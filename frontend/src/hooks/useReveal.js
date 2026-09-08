import { useEffect, useRef } from 'react';

/**
 * Attaches an IntersectionObserver to the returned ref and adds
 * `is-visible` once the element scrolls into view. Pair with the
 * `.reveal` or `.reveal-stagger` classes in index.css.
 */
export function useReveal(threshold = 0.15) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold]);

  return ref;
}
