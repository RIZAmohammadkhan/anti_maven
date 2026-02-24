import { useRef } from 'react';
import { marked } from 'marked';
import ProductCard from './ProductCard';

export default function ResultsView({ results, products, onOpenDrawer, onNewSearch }) {
  const carouselRef = useRef(null);

  function scrollCarousel(direction) {
    if (carouselRef.current) {
      carouselRef.current.scrollBy({ left: direction * 360, behavior: 'smooth' });
    }
  }

  return (
    <section className="animate-fade-in-up">
      {/* AI Recommendation */}
      <div className="bg-white rounded-3xl p-8 mb-12 shadow-sm border border-gray-100 flex flex-col md:flex-row gap-6 items-start">
        <div className="bg-brand-soft p-4 rounded-2xl text-brand-orange shrink-0">
          <i className="fa-solid fa-wand-magic-sparkles text-2xl"></i>
        </div>
        <div
          className="prose prose-sm max-w-none text-gray-600 recommendation-text"
          dangerouslySetInnerHTML={{ __html: marked.parse(results.final_recommendation || 'Here are your top results.') }}
        />
      </div>

      {/* Carousel Controls */}
      <div className="flex justify-between items-end mb-6 px-2">
        <div>
          <h2 className="font-display text-3xl font-bold">Top Picks</h2>
          <p className="text-gray-400 text-sm mt-1">Found across major retailers</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => scrollCarousel(-1)}
            className="w-12 h-12 rounded-full bg-white border border-gray-200 hover:border-brand-orange hover:text-brand-orange flex items-center justify-center transition-all shadow-sm"
          >
            <i className="fa-solid fa-arrow-left"></i>
          </button>
          <button
            onClick={() => scrollCarousel(1)}
            className="w-12 h-12 rounded-full bg-brand-black text-white hover:bg-brand-orange flex items-center justify-center transition-all shadow-lg shadow-brand-black/20"
          >
            <i className="fa-solid fa-arrow-right"></i>
          </button>
        </div>
      </div>

      {/* Carousel */}
      <div
        ref={carouselRef}
        className="flex gap-6 overflow-x-auto no-scrollbar snap-x snap-mandatory py-4 px-2 pb-12"
        style={{ scrollBehavior: 'smooth' }}
      >
        {products.map((product, index) => (
          <ProductCard
            key={index}
            product={product}
            onDetails={() => onOpenDrawer(product)}
          />
        ))}
      </div>

      <div className="text-center mt-8">
        <button
          onClick={onNewSearch}
          className="text-gray-400 hover:text-brand-orange text-sm font-medium transition-colors"
        >
          <i className="fa-solid fa-rotate-right mr-2"></i>Start New Search
        </button>
      </div>
    </section>
  );
}
