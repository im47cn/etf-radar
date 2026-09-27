-- factory 仲裁层 schema（幂等迁移；psql "$SUPABASE_DB" -f 本文件）
--
-- 三层架构（README「租约仲裁」节）：
--   仲裁 = 本 schema（Supabase/Postgres，线性化，唯一权威回答"轮到谁"）
--   投影 = GitHub labels + state.py（声明式收敛，sync 多写者安全）
--   围栏 = git refs 服务端保护（factory/* 禁 force push/禁删）
--
-- 安全模型：
--   每租户一个 PG login role（factory_tenants.rolname ↔ session_user），
--   身份由连接串自证，客户端不可自报租户。worker 函数 SECURITY DEFINER
--   （owner=应用 schema 的角色），表权限全收——自定义 role 只有 EXECUTE。
--   RLS 全开且不建任何 policy：经 PostgREST/anon 的直表读写全拒。
--   吊销（factory_revoke）仅管理员（postgres/supabase_admin）可调。
--
-- 认证注：SECURITY DEFINER 体内 current_user=owner，故租户解析一律用
--   session_user（登录 role，不可伪造）。

-- ── 表 ──────────────────────────────────────────────────────────────

create table if not exists factory_tenants (
  tenant       text primary key,
  rolname      text unique not null,                 -- 登录 role 名
  status       text not null default 'active' check (status in ('active', 'disabled')),
  max_parallel int  not null default 2 check (max_parallel >= 0)  -- 租户并发租约上限（配额=公平）
);

create table if not exists factory_machines (
  machine_id text primary key,                       -- .factory/var/machine-id（非 PID）
  tenant     text not null references factory_tenants(tenant),
  status     text not null default 'active' check (status in ('active', 'disabled')),
  first_seen timestamptz not null default now(),
  last_seen  timestamptz not null default now()
);

create table if not exists factory_leases (
  key          text primary key,                     -- 'issue:42' / 'pr:7'
  tenant       text not null,
  machine_id   text not null,
  epoch        bigint not null default 0,            -- 每次易主 +1：fencing token
  heartbeat_at timestamptz not null default now(),
  expires_at   timestamptz not null default now()
);

create table if not exists factory_events (          -- 审计（跨机可见性）
  ts         timestamptz not null default now(),
  tenant     text not null,
  machine_id text not null,
  key        text not null,
  action     text not null,                          -- claim|reclaim|release|revoke
  epoch      bigint not null
);

-- ── worker 函数（security definer；session_user 解析租户） ──────────

-- claim：原子认领。赢 = 唯一插入者，或续约（同机同租户，epoch 不变），
-- 或接管（租约已过期，epoch+1）。输 = 其余一切，含未激活租户/机器、超配额。
create or replace function factory_claim(p_key text, p_machine text, p_secs int)
returns table (o_won boolean, o_epoch bigint)
language plpgsql security definer set search_path = public as $$
declare
  v_tenant text; v_cap int; v_e bigint;
begin
  -- for update：串行化同租户并发 claim（行锁持到事务尾），否则
  -- 配额 count-then-insert 是 TOCTOU——两机同时观察到余量并双双插入。
  select t.tenant, t.max_parallel into v_tenant, v_cap
    from factory_tenants t
   where t.rolname = session_user and t.status = 'active'
   for update;
  if not found then
    return query select false, -1::bigint; return;
  end if;

  -- 机器自注册（身份=观测标签；授权在 role 层）。被管理员停用的机器拒绝。
  insert into factory_machines as m (machine_id, tenant)
  values (p_machine, v_tenant)
  on conflict (machine_id) do update set last_seen = now();
  if exists (select 1 from factory_machines
              where machine_id = p_machine and status <> 'active') then
    return query select false, -1::bigint; return;
  end if;

  -- 配额：本租户活跃租约（不含本键——自己的续约不许被自己堵）
  if (select count(*) from factory_leases
       where tenant = v_tenant and expires_at > now() and key <> p_key) >= v_cap then
    return query select false, -1::bigint; return;
  end if;

  insert into factory_leases (key, tenant, machine_id, epoch, expires_at)
  values (p_key, v_tenant, p_machine, 1, now() + make_interval(secs => p_secs))
  on conflict (key) do nothing;
  if found then
    insert into factory_events (tenant, machine_id, key, action, epoch)
    values (v_tenant, p_machine, p_key, 'claim', 1);
    return query select true, 1::bigint; return;
  end if;

  update factory_leases as l
     set tenant = v_tenant,
         machine_id = p_machine,
         epoch = l.epoch + (case when l.machine_id = p_machine then 0 else 1 end),
         heartbeat_at = now(),
         expires_at = now() + make_interval(secs => p_secs)
   where l.key = p_key
     and (l.expires_at <= now()                                    -- 过期可抢
          or (l.machine_id = p_machine and l.tenant = v_tenant))   -- 自己续约
  returning l.epoch into v_e;
  if v_e is null then
    return query select false, -1::bigint;
  else
    insert into factory_events (tenant, machine_id, key, action, epoch)
    values (v_tenant, p_machine, p_key, 'reclaim', v_e);
    return query select true, v_e;
  end if;
end $$;

-- heartbeat：续租。同键+同机+同 epoch+未过期才成功；任何不匹配 = 已被夺走
-- （接管/吊销/过期），调用方必须立即终止链。epoch 不变。
create or replace function factory_heartbeat(p_key text, p_machine text, p_epoch bigint, p_secs int)
returns boolean
language plpgsql security definer set search_path = public as $$
declare v_tenant text;
begin
  select tenant into v_tenant from factory_tenants
   where rolname = session_user and status = 'active';
  if not found then return false; end if;
  if exists (select 1 from factory_machines
              where machine_id = p_machine and status <> 'active') then
    return false;
  end if;
  update factory_machines set last_seen = now() where machine_id = p_machine;
  update factory_leases as l
     set heartbeat_at = now(), expires_at = now() + make_interval(secs => p_secs)
   where l.key = p_key and l.machine_id = p_machine and l.epoch = p_epoch
     and l.tenant = v_tenant
     and l.expires_at > now();                       -- 已过期不许复活，须重新 claim
  return found;
end $$;

-- fence_ok：不可逆动作前的围栏校验（决策点 fencing；GitHub 无条件写，
-- 秒级残窗由评论幂等键兜底，见 factory-lib.sh issue_comment）。
create or replace function factory_fence_ok(p_key text, p_machine text, p_epoch bigint)
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1
      from factory_leases l
      join factory_machines m on m.machine_id = l.machine_id
      join factory_tenants t on t.tenant = l.tenant
     where l.key = p_key and l.machine_id = p_machine and l.epoch = p_epoch
       and l.tenant = (select tenant from factory_tenants where rolname = session_user)
       and l.expires_at > now()
       and t.status = 'active' and m.status = 'active'
  )
$$;

-- release：主动释放（链正常退出）。不升 epoch（下次易主自会 +1），
-- expires_at=now() 使键立即可被他人认领。
create or replace function factory_release(p_key text, p_machine text, p_epoch bigint)
returns boolean
language plpgsql security definer set search_path = public as $$
declare v_tenant text;
begin
  select tenant into v_tenant from factory_tenants where rolname = session_user;
  if not found then return false; end if;
  update factory_leases as l
     set expires_at = now(), heartbeat_at = now()
   where l.key = p_key and l.machine_id = p_machine and l.epoch = p_epoch
     and l.tenant = v_tenant;
  if found then
    insert into factory_events (tenant, machine_id, key, action, epoch)
    values (v_tenant, p_machine, p_key, 'release', p_epoch);
  end if;
  return found;
end $$;

-- ── 管理员函数（仅 postgres/supabase_admin）────────────────────────

-- 吊销租户：status=disabled + 其全部活跃租约立即过期并 epoch+1——
-- 被吊销者的下一次心跳/fence 必失败（epoch 对不上），无需等租约自然过期。
create or replace function factory_revoke(p_tenant text)
returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if session_user not in ('postgres', 'supabase_admin') then
    raise exception 'factory_revoke 仅限管理员（当前 session_user=%）', session_user;
  end if;
  update factory_tenants set status = 'disabled'
   where tenant = p_tenant and status <> 'disabled';
  get diagnostics n = row_count;
  with dead as (
    update factory_leases set expires_at = now(), epoch = epoch + 1
     where tenant = p_tenant and expires_at > now()
    returning key, machine_id, epoch
  )
  insert into factory_events (tenant, machine_id, key, action, epoch)
  select p_tenant, machine_id, key, 'revoke', epoch from dead;
  return n;
end $$;

-- 停用单台机器（精确止损：失控的是一台机器，不是一个人）。
create or replace function factory_machine_disable(p_machine text)
returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if session_user not in ('postgres', 'supabase_admin') then
    raise exception 'factory_machine_disable 仅限管理员（当前 session_user=%）', session_user;
  end if;
  update factory_machines set status = 'disabled'
   where machine_id = p_machine and status <> 'disabled';
  get diagnostics n = row_count;
  with dead as (
    update factory_leases set expires_at = now(), epoch = epoch + 1
     where machine_id = p_machine and expires_at > now()
    returning key, tenant, epoch
  )
  insert into factory_events (tenant, machine_id, key, action, epoch)
  select tenant, p_machine, key, 'revoke', epoch from dead;
  return n;
end $$;

-- ── 权限收口 ────────────────────────────────────────────────────────

alter table factory_tenants  enable row level security;
alter table factory_machines enable row level security;
alter table factory_leases   enable row level security;
alter table factory_events   enable row level security;
-- 故意不建任何 policy：RLS 开而无 policy = 全拒（PostgREST/anon 直表全封）。

-- PG 默认给 PUBLIC 授函数 EXECUTE：先全收。Supabase 侧角色存在才收（本地库无）。
revoke all on function factory_claim(text, text, integer) from public;
revoke all on function factory_heartbeat(text, text, bigint, integer) from public;
revoke all on function factory_release(text, text, bigint) from public;
revoke all on function factory_fence_ok(text, text, bigint) from public;
revoke all on function factory_revoke(text) from public;
revoke all on function factory_machine_disable(text) from public;
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on factory_tenants, factory_machines, factory_leases, factory_events from %I', r);
      execute format('revoke all on function factory_claim(text, text, integer) from %I', r);
      execute format('revoke all on function factory_heartbeat(text, text, bigint, integer) from %I', r);
      execute format('revoke all on function factory_release(text, text, bigint) from %I', r);
      execute format('revoke all on function factory_fence_ok(text, text, bigint) from %I', r);
    end if;
  end loop;
end $$;

-- worker 组角色：租户 onboarding = create role + grant 本组 + insert 租户行
-- （README 运维手册）。组不存在则创建（首次迁移）。
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'factory_worker') then
    create role factory_worker nologin;
  end if;
end $$;
grant execute on function factory_claim(text, text, integer) to factory_worker;
grant execute on function factory_heartbeat(text, text, bigint, integer) to factory_worker;
grant execute on function factory_release(text, text, bigint) to factory_worker;
grant execute on function factory_fence_ok(text, text, bigint) to factory_worker;
