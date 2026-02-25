import { useState } from 'react';

export default function PersonalizationModal({ questions, onSubmit, onSkip }) {
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

  function handleChange(qid, value) {
    setAnswers((prev) => ({ ...prev, [qid]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    await onSubmit(answers);
  }

  return (
    <section className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in-up">
      <div className="w-full max-w-2xl bg-white border border-gray-100 rounded-3xl shadow-sm p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-brand-soft rounded-2xl flex items-center justify-center text-brand-orange">
            <i className="fa-solid fa-sliders"></i>
          </div>
          <div>
            <h2 className="font-display text-2xl font-bold text-brand-black">Personalize your results</h2>
            <p className="text-gray-500 text-sm">Answer a few quick questions so Maven can tailor recommendations.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {questions.map((q) => (
            <div key={q.id} className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">{q.question}</label>
              {q.type === 'select' && q.options?.length > 0 ? (
                <div className="relative">
                  <select
                    value={answers[q.id] || ''}
                    onChange={(e) => handleChange(q.id, e.target.value)}
                    className="w-full py-3 px-4 pr-10 bg-white border border-gray-200 rounded-xl text-brand-black focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all appearance-none"
                  >
                    <option value="">Select...</option>
                    {q.options.map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                    <i className="fa-solid fa-chevron-down text-gray-400"></i>
                  </div>
                </div>
              ) : (
                <input
                  type="text"
                  value={answers[q.id] || ''}
                  onChange={(e) => handleChange(q.id, e.target.value)}
                  className="w-full py-3 px-4 bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all"
                  placeholder="Type your answer..."
                />
              )}
            </div>
          ))}

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              type="button"
              onClick={onSkip}
              disabled={submitting}
              className="w-full sm:w-auto py-3 px-5 rounded-xl border border-gray-200 text-sm font-medium text-gray-600 hover:border-brand-black hover:text-brand-black transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Skip
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="w-full sm:flex-1 py-3 px-5 rounded-xl bg-brand-black text-white text-sm font-medium hover:bg-brand-orange transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Starting research…
                </>
              ) : 'Start research'}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
