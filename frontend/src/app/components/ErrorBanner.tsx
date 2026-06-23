interface ErrorBannerProps {
  message: string
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700"
    >
      <span aria-hidden className="mt-0.5 font-bold">!</span>
      <span>{message}</span>
    </div>
  )
}
