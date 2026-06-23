interface Props {
  message: string;
}

export const EmptyState = ({ message }: Props) => (
  <div
    role="status"
    className="py-12 text-center text-sm text-gray-500 border border-dashed border-gray-300 rounded-lg"
  >
    {message}
  </div>
);
