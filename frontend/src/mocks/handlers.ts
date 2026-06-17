import { http, HttpResponse } from 'msw';
import { mkIndex, mkFrame } from '@/__fixtures__/snapshots';

export const handlers = [
  http.get('*/snapshots-index.json', () => HttpResponse.json(mkIndex(5))),
  http.get('*/snapshots/:date/themes.json', ({ params }) => {
    const date = params.date as string;
    return HttpResponse.json({
      schema_version: '1.0',
      generated_at: `${date}T00:00:00+08:00`,
      themes: mkFrame(date).themes,
    });
  }),
];
