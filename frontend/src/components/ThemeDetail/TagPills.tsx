import { Badge } from '@/components/ui/badge';

export const TagPills = ({ tags }: { tags: string[] }) => (
  <div className="flex flex-wrap gap-1">
    {tags.map((t) => (
      <Badge key={t} variant="outline">
        {t}
      </Badge>
    ))}
  </div>
);
