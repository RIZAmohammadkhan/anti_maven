import { generateStars, formatPrice } from '../utils';

export default function ProductDrawer({ product, onClose }) {
  if (!product) return null;

  const bestPrice = formatPrice(product.price);
  const cheapestLink = product.cheapest_link || product.url;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50 transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 w-full md:w-[500px] bg-white shadow-2xl z-50 animate-slide-in-right flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-white sticky top-0 z-10">
          <h3 className="font-display text-xl font-bold text-brand-black truncate pr-4">
            {product.name}
          </h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-gray-50 hover:bg-gray-100 flex items-center justify-center transition-colors"
          >
            <i className="fa-solid fa-times text-gray-400"></i>
          </button>
        </div>

        {/* Content */}
        <div className="flex-grow overflow-y-auto p-6 space-y-8">
          {/* Price & Rating */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <span className="block text-sm text-gray-500">Best Price</span>
              <span className="text-2xl font-bold text-brand-black">{bestPrice}</span>
            </div>
            <div className="text-right">
              <div className="flex items-center gap-2 justify-end mb-1">
                <div
                  className="flex text-brand-orange text-base"
                  dangerouslySetInnerHTML={{ __html: generateStars(product.rating) }}
                />
                <span className="text-lg font-bold text-brand-black">{product.rating || 'N/A'}</span>
              </div>
              <span className="text-xs text-gray-400">{product.reviews_count || 'Verified'} Reviews</span>
            </div>
          </div>

          {/* Why to buy */}
          {product.why_to_buy && (
            <div className="bg-brand-soft/50 p-4 rounded-xl border border-brand-orange/10">
              <div className="flex gap-3">
                <i className="fa-solid fa-quote-left text-brand-orange/40 text-xl"></i>
                <p className="text-sm text-gray-700 italic leading-relaxed">{product.why_to_buy}</p>
              </div>
            </div>
          )}

          {/* Price Comparison */}
          {product.price_comparison && product.price_comparison.length > 0 && (
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Price Comparison</h4>
              <div className="space-y-3">
                {product.price_comparison.map((p, idx) => (
                  <div key={idx} className="flex justify-between items-center text-sm">
                    <span className="font-medium text-gray-700">{p.retailer}</span>
                    <div className="flex items-center gap-3">
                      <span className="font-bold">{formatPrice(p.price)}</span>
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-brand-orange hover:text-brand-black">
                        <i className="fa-solid fa-external-link-alt"></i>
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pros */}
          {product.pros && product.pros.length > 0 && (
            <div>
              <h4 className="font-bold flex items-center gap-2 mb-3 text-sm">
                <i className="fa-solid fa-check-circle text-green-500"></i> The Good
              </h4>
              <ul className="space-y-2">
                {product.pros.map((pro, idx) => (
                  <li key={idx} className="text-sm text-gray-600 pl-2 border-l-2 border-green-100">{pro}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Cons */}
          {product.cons && product.cons.length > 0 && (
            <div>
              <h4 className="font-bold flex items-center gap-2 mb-3 text-sm">
                <i className="fa-solid fa-circle-exclamation text-red-400"></i> The Bad
              </h4>
              <ul className="space-y-2">
                {product.cons.map((con, idx) => (
                  <li key={idx} className="text-sm text-gray-600 pl-2 border-l-2 border-red-100">{con}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Features */}
          {product.features && Array.isArray(product.features) && product.features.length > 0 && (
            <div>
              <h4 className="font-bold text-sm mb-3">Key Features</h4>
              <div className="flex flex-wrap gap-2">
                {product.features.map((f, idx) => (
                  <span key={idx} className="px-3 py-1 bg-gray-100 rounded-lg text-xs text-gray-600 border border-gray-200">
                    {String(f).split(':')[0]}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-100 bg-gray-50">
          <a
            href={cheapestLink}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full py-4 bg-brand-black text-white rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-brand-orange transition-all shadow-xl shadow-brand-orange/20"
          >
            <span>Buy Now for {bestPrice}</span>
            <i className="fa-solid fa-arrow-right"></i>
          </a>
        </div>
      </div>
    </>
  );
}
