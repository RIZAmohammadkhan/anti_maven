export function formatPrice(price) {
  if (!price) return 'Check Price';
  if (typeof price === 'string' && price.includes('$')) return price;
  const num = parseFloat(price);
  return isNaN(num) ? String(price) : `$${num.toFixed(2)}`;
}

export function generateStars(rating) {
  const r = parseFloat(rating) || 0;
  let html = '';
  for (let i = 1; i <= 5; i++) {
    if (i <= Math.floor(r)) {
      html += '<i class="fa-solid fa-star"></i>';
    } else if (i === Math.ceil(r) && !Number.isInteger(r)) {
      html += '<i class="fa-solid fa-star-half-stroke"></i>';
    } else {
      html += '<i class="fa-regular fa-star text-gray-300"></i>';
    }
  }
  return html;
}
