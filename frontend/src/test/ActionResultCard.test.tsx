import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ActionResultCard } from '@/components/ActionCard';
import type { ActionCard } from '@/lib/types';

const renderCard = (card: ActionCard, liveStatus?: string | null) =>
  render(<MemoryRouter><ActionResultCard card={card} liveStatus={liveStatus} /></MemoryRouter>);

describe('ActionResultCard never overstates a financial outcome', () => {
  it('says completed only when PayPal confirmed it', () => {
    renderCard({ kind: 'refund', action_state: 'SUCCEEDED', refund_status: 'COMPLETED' });
    expect(screen.getByText('Refund completed by PayPal')).toBeInTheDocument();
  });
  it('shows waiting for approval when the policy requires a manager', () => {
    renderCard({ kind: 'refund', action_state: 'AWAITING_APPROVAL', decision: 'REQUIRES_APPROVAL' });
    expect(screen.getByText('Waiting for manager approval')).toBeInTheDocument();
    expect(screen.queryByText(/completed/i)).not.toBeInTheDocument();
  });
  it('does not claim success when the outcome is unknown', () => {
    renderCard({ kind: 'refund', action_state: 'OUTCOME_UNKNOWN' });
    expect(screen.getByText(/waiting for PayPal confirmation/)).toBeInTheDocument();
    expect(screen.queryByText('Refund completed by PayPal')).not.toBeInTheDocument();
  });
  it('lets a later live failure override an earlier card', () => {
    renderCard({ kind: 'refund', action_state: 'SUCCEEDED' }, 'FAILED');
    expect(screen.getByText('Refund could not be completed')).toBeInTheDocument();
    expect(screen.queryByText('Refund completed by PayPal')).not.toBeInTheDocument();
  });
  it('shows escalations honestly', () => {
    renderCard({ kind: 'refund', decision: 'ESCALATED', action_state: 'ESCALATED' });
    expect(screen.getByText('Escalated for manual review')).toBeInTheDocument();
  });
});
