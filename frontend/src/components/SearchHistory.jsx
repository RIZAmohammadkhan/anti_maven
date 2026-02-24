export default function SearchHistory({ history, loading, onView, onDelete, onReSearch }) {
  if (loading) {
    return (
      <div className="w-full max-w-4xl">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-4 h-4 border-2 border-brand-orange border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-400">Loading history...</span>
        </div>
      </div>
    );
  }

  if (!history || history.length === 0) {
    return (
      <div className="w-full max-w-4xl text-center">
        <div className="bg-white rounded-2xl border border-gray-100 p-8">
          <i className="fa-solid fa-clock-rotate-left text-3xl text-gray-200 mb-3"></i>
          <p className="text-gray-400 text-sm">Your recent searches will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl">
      <div className="flex items-center gap-2 mb-4">
        <i className="fa-solid fa-clock-rotate-left text-gray-400"></i>
        <h3 className="font-display font-bold text-lg text-brand-black">Recent Searches</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {history.slice(0, 9).map((item) => (
          <div
            key={item.id}
            className="bg-white rounded-2xl border border-gray-100 p-5 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 group"
          >
            <div className="flex items-start justify-between mb-3">
              <h4 className="font-medium text-brand-black text-sm line-clamp-2 flex-1 pr-2">
                {item.query}
              </h4>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(item.id); }}
                className="text-gray-300 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                title="Delete"
              >
                <i className="fa-solid fa-trash-can text-xs"></i>
              </button>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-gray-400">
                {item.products?.length || 0} products found
              </span>
              <span className="text-gray-200">·</span>
              <span className="text-xs text-gray-400">
                {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
              </span>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => onView(item)}
                className="flex-1 py-2 px-3 rounded-lg bg-gray-50 hover:bg-brand-soft text-xs font-medium text-gray-600 hover:text-brand-orange transition-colors"
              >
                <i className="fa-solid fa-eye mr-1.5"></i>View
              </button>
              <button
                onClick={() => onReSearch(item.query)}
                className="flex-1 py-2 px-3 rounded-lg bg-gray-50 hover:bg-brand-black text-xs font-medium text-gray-600 hover:text-white transition-colors"
              >
                <i className="fa-solid fa-rotate-right mr-1.5"></i>Re-search
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
