// 纯 TS MD5 实现（零依赖）。afdian 验签需要 md5，而 Web Crypto 不支持 MD5，
// std/crypto 的 wasm 模块在部分 Deno 版本下加载异常，故内置一份。
// 算法来自 RFC 1321，仅用于验签，非安全散列用途。

function toBytes(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

function rotl(x: number, c: number): number {
  return (x << c) | (x >>> (32 - c));
}

export function md5Hex(input: string): string {
  const msg = toBytes(input);
  const origLenBits = msg.length * 8;

  // padding
  const withOne = msg.length + 1;
  const padLen = ((56 - (withOne % 64)) + 64) % 64;
  const total = withOne + padLen + 8;
  const buf = new Uint8Array(total);
  buf.set(msg);
  buf[msg.length] = 0x80;
  // 写入 64 位长度（小端）
  const lenLo = origLenBits >>> 0;
  const lenHi = Math.floor(origLenBits / 0x100000000) >>> 0;
  const dv = new DataView(buf.buffer);
  dv.setUint32(total - 8, lenLo, true);
  dv.setUint32(total - 4, lenHi, true);

  // 每步左移量
  const s = [
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
  ];
  // 常量表 K[i] = floor(2^32 * abs(sin(i+1)))
  const K = new Int32Array(64);
  for (let i = 0; i < 64; i++) {
    K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 0x100000000) | 0;
  }

  let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;

  for (let off = 0; off < total; off += 64) {
    const M = new Int32Array(16);
    for (let i = 0; i < 16; i++) {
      M[i] = dv.getUint32(off + i * 4, true) | 0;
    }
    let A = a0, B = b0, C = c0, D = d0;
    for (let i = 0; i < 64; i++) {
      let F: number, g: number;
      if (i < 16) {
        F = (B & C) | (~B & D);
        g = i;
      } else if (i < 32) {
        F = (D & B) | (~D & C);
        g = (5 * i + 1) % 16;
      } else if (i < 48) {
        F = B ^ C ^ D;
        g = (3 * i + 5) % 16;
      } else {
        F = C ^ (B | ~D);
        g = (7 * i) % 16;
      }
      F = (F + A + K[i] + M[g]) | 0;
      A = D;
      D = C;
      C = B;
      B = (B + rotl(F, s[i])) | 0;
    }
    a0 = (a0 + A) | 0;
    b0 = (b0 + B) | 0;
    c0 = (c0 + C) | 0;
    d0 = (d0 + D) | 0;
  }

  const out = new Uint8Array(16);
  const odv = new DataView(out.buffer);
  odv.setUint32(0, a0 >>> 0, true);
  odv.setUint32(4, b0 >>> 0, true);
  odv.setUint32(8, c0 >>> 0, true);
  odv.setUint32(12, d0 >>> 0, true);
  return Array.from(out, (b) => b.toString(16).padStart(2, "0")).join("");
}
