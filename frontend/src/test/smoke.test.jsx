import { describe, it, expect } from 'vitest';

/**
 * Smoke test: verifies the test runner is wired and core math works.
 * Replace / expand with component tests once the design system stabilises.
 */
describe('frontend smoke', () => {
  it('does basic math', () => {
    expect(2 + 2).toBe(4);
  });

  it('has a working DOM', () => {
    const el = document.createElement('div');
    el.textContent = 'hello';
    expect(el.textContent).toBe('hello');
  });
});
