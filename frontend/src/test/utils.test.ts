import { describe, expect, it } from 'vitest';
import { humanize, money, pct } from '@/lib/utils';

describe('formatting helpers', () => {
  it('formats INR with Indian grouping', () => {
    expect(money('545969', 'INR')).toBe('₹5,45,969.00');
  });
  it('formats USD', () => {
    expect(money(12.5, 'USD')).toBe('$12.50');
  });
  it('shows a dash for missing amounts instead of zero', () => {
    expect(money(null)).toBe('—');
    expect(money('')).toBe('—');
  });
  it('humanizes enum values', () => {
    expect(humanize('REQUIRES_APPROVAL')).toBe('Requires approval');
  });
  it('formats ratios', () => {
    expect(pct(0.343)).toBe('34%');
    expect(pct(null)).toBe('—');
  });
});
