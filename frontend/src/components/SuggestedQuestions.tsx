'use client'

interface SuggestedQuestionsProps {
  questions: string[]
  onPick: (q: string) => void
}

export function SuggestedQuestions({
  questions,
  onPick,
}: SuggestedQuestionsProps) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        Suggested questions
      </p>
      <div className="flex flex-wrap gap-2" data-testid="suggested-questions">
        {questions.map((q, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
