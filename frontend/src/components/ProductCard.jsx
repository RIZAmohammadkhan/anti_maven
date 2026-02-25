import { useState } from 'react';
import { generateStars, formatPrice } from '../utils';

function ProductImage({ src, alt }) {
  const [failed, setFailed] = useState(false);
  const proxied = src ? `/api/image-proxy?url=${encodeURIComponent(src)}` : null;

  if (!proxied || failed) {
    return (
      <div className="w-full h-48 bg-gradient-to-br from-gray-100 to-gray-50 flex items-center justify-center">
        <i className="fa-solid fa-box-open text-4xl text-gray-300"></i>
      </div>
    );
  }

  return (
    <img
      src={proxied}
      alt={alt}
      className="w-full h-48 object-contain bg-white p-2"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export default function ProductCard({ product, onDetails }) {
  const rating = product.rating || 4.0;
  const bestPrice = formatPrice(product.price);
  const cheapestLink = product.cheapest_link || product.url;

  return (
    <div className="min-w-[300px] md:min-w-[340px] snap-center bg-white rounded-3xl border border-gray-100 shadow-lg shadow-gray-200/50 hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col overflow-hidden group h-full">
      {/* Product Image */}
      <ProductImage src={product.image_url} alt={product.name} />

      <div className="p-6 flex flex-col flex-grow">
        {/* Rating */}
        <div className="flex items-center gap-2 mb-3">
          <div
            className="flex text-brand-orange text-sm"
            dangerouslySetInnerHTML={{ __html: generateStars(rating) }}
          />
          <span className="text-sm font-bold text-brand-black">{rating}</span>
          <span className="text-xs text-gray-400 font-medium">
            ({product.reviews_count ? `${product.reviews_count} reviews` : 'Top Rated'})
          </span>
        </div>

        {/* Name */}
        <h3
          className="font-display font-bold text-lg leading-tight mb-2 line-clamp-2 h-12"
          title={product.name}
        >
          {product.name}
        </h3>

        {/* Price */}
        <div className="flex items-baseline gap-2 mb-4">
          <span className="text-2xl font-bold text-brand-black">{bestPrice}</span>
        </div>

        {/* Why to buy snippet */}
        {product.why_to_buy && (
          <p className="text-xs text-gray-500 line-clamp-2 mb-4 italic">
            "{product.why_to_buy}"
          </p>
        )}

        {/* Actions */}
        <div className="mt-auto pt-4 grid grid-cols-2 gap-3">
          <button
            onClick={onDetails}
            className="py-2.5 px-4 rounded-xl border border-gray-200 text-sm font-medium text-gray-600 hover:border-brand-black hover:text-brand-black transition-colors"
          >
            Details
          </button>
          <a
            href={cheapestLink}
            target="_blank"
            rel="noopener noreferrer"
            className="py-2.5 px-4 rounded-xl bg-brand-black text-white text-sm font-medium flex items-center justify-center gap-2 hover:bg-brand-orange transition-colors shadow-lg shadow-brand-black/20"
          >
            Buy Now
          </a>
        </div>
      </div>
    </div>
  );
}
