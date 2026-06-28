interface Props {
  inputTokens: number
  outputTokens: number
  costUsd: number
}

export default function CostFooter({ inputTokens, outputTokens, costUsd }: Props) {
  return (
    <div className="mt-3 flex items-center gap-4 text-xs text-gray-400 border-t border-gray-100 pt-2">
      <span>Tokens: {(inputTokens + outputTokens).toLocaleString()} ({inputTokens.toLocaleString()} in / {outputTokens.toLocaleString()} out)</span>
      <span>Cost: ${costUsd.toFixed(5)}</span>
    </div>
  )
}
