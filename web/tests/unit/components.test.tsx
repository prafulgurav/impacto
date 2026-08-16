import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import AmbiguityCallout from '@/components/AmbiguityCallout';
import ChannelChip from '@/components/ChannelChip';
import CitationList from '@/components/CitationList';
import DisclaimerBar from '@/components/DisclaimerBar';
import EvidenceBadge from '@/components/EvidenceBadge';
import StatTile from '@/components/StatTile';
import CarDistribution from '@/components/charts/CarDistribution';
import ImpactBars, { type ImpactBarRow } from '@/components/charts/ImpactBars';
import { eligible } from '@/components/InstallPrompt';
import copy from '@/lib/copy/en-IN';

describe('EvidenceBadge', () => {
  it('always shows the sample size and the p-value', () => {
    render(<EvidenceBadge sampleSize={33} pValue={0.041} />);
    expect(screen.getByText(/n=33/)).toBeInTheDocument();
    expect(screen.getByText(/p=0\.041/)).toBeInTheDocument();
  });

  it('says plainly when the distribution is not distinguishable from noise', () => {
    render(<EvidenceBadge sampleSize={33} pValue={0.77} />);
    expect(screen.getByText(copy.evidence.noise)).toBeInTheDocument();
  });

  it('stays silent about noise below the threshold', () => {
    render(<EvidenceBadge sampleSize={33} pValue={0.02} />);
    expect(screen.queryByText(copy.evidence.noise)).not.toBeInTheDocument();
  });

  it('reports a p-value below 0.001 as a bound, not false precision', () => {
    render(<EvidenceBadge sampleSize={40} pValue={0.00004} />);
    expect(screen.getByText(/p=<0\.001/)).toBeInTheDocument();
  });

  it('announces the caveat together with the figure for screen readers', () => {
    render(<EvidenceBadge sampleSize={12} pValue={0.9} />);
    const label = screen.getByLabelText(/Based on 12 past occurrences/);
    expect(label).toHaveAccessibleName(new RegExp(copy.evidence.noise));
  });
});

describe('StatTile', () => {
  it('renders label, value and evidence together', () => {
    render(
      <StatTile
        label="Median"
        value="−180 bps"
        evidence={{ sampleSize: 12, pValue: 0.04 }}
      />,
    );
    expect(screen.getByText('Median')).toBeInTheDocument();
    expect(screen.getByText('−180 bps')).toBeInTheDocument();
    expect(screen.getByText(/n=12/)).toBeInTheDocument();
  });

  it('keeps the figure on one line', () => {
    render(<StatTile label="Median" value="−1,180 bps" />);
    expect(screen.getByText('−1,180 bps').className).toContain('whitespace-nowrap');
  });
});

const ROWS: ImpactBarRow[] = [
  {
    target: 'NIFTY_IT',
    label: 'Nifty It',
    direction: -1,
    priorLowBps: -250,
    priorHighBps: -80,
    realisedMedianBps: -180,
    sampleSize: 12,
    pValue: 0.04,
  },
  {
    target: 'NIFTY_BANK',
    label: 'Nifty Bank',
    direction: 0,
    priorLowBps: -100,
    priorHighBps: 100,
    realisedMedianBps: 15,
    sampleSize: 9,
    pValue: 0.62,
  },
];

describe('ImpactBars', () => {
  it('renders a chart at width', () => {
    render(<ImpactBars rows={ROWS} />);
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('explains the encoding rather than leaving the marks unlabelled', () => {
    render(<ImpactBars rows={ROWS} />);
    expect(screen.getByText(copy.charts.impactBarsLegendBar)).toBeInTheDocument();
    expect(screen.getByText(copy.charts.impactBarsLegendDot)).toBeInTheDocument();
  });

  it('degrades to a list below 480px rather than shrinking the chart', () => {
    render(<ImpactBars rows={ROWS} forceCompact />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    // Every number still carries its evidence in the fallback.
    expect(within(items[0]!).getByText(/n=12/)).toBeInTheDocument();
  });

  it('says so when there is nothing to plot', () => {
    render(<ImpactBars rows={[]} />);
    expect(screen.getByText(copy.charts.noData)).toBeInTheDocument();
  });
});

const POINTS = [
  { eventId: 'a', eventDate: '2024-01-02', headline: 'A', carBps: -220 },
  { eventId: 'b', eventDate: '2024-04-11', headline: 'B', carBps: -60 },
  { eventId: 'c', eventDate: '2024-09-30', headline: 'C', carBps: 90 },
];

describe('CarDistribution', () => {
  it('draws a histogram with the median rule at width', () => {
    render(<CarDistribution points={POINTS} medianBps={-60} />);
    expect(screen.getByRole('img')).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(copy.charts.distributionMedianRule)),
    ).toBeInTheDocument();
  });

  it('switches to a strip plot below 480px', () => {
    render(<CarDistribution points={POINTS} medianBps={-60} forceCompact />);
    expect(screen.getByText(new RegExp(copy.charts.stripPlotHint))).toBeInTheDocument();
  });

  it('handles an empty sample', () => {
    render(<CarDistribution points={[]} medianBps={0} />);
    expect(screen.getByText(copy.charts.noData)).toBeInTheDocument();
  });
});

describe('AmbiguityCallout', () => {
  it('states that the mechanism cuts both ways instead of picking a sign', () => {
    render(<AmbiguityCallout />);
    expect(screen.getByText(copy.ambiguity.heading)).toBeInTheDocument();
    expect(screen.getByText(copy.ambiguity.body)).toBeInTheDocument();
  });
});

describe('DisclaimerBar', () => {
  it('is present and offers no way to dismiss it', () => {
    const { container } = render(<DisclaimerBar />);
    expect(screen.getByRole('note')).toBeInTheDocument();
    expect(container.querySelector('button')).toBeNull();
  });

  it('is sticky rather than scrolled away', () => {
    render(<DisclaimerBar />);
    expect(screen.getByRole('note').className).toContain('sticky');
  });
});

describe('ChannelChip', () => {
  const channel = {
    id: 'usd_rev',
    name: 'USD revenue translation',
    kind: 'earnings',
    horizon: 'fast' as const,
    description: 'A weaker rupee raises the rupee value of dollar revenue.',
  };

  it('keeps the mechanism one tap away', async () => {
    const user = userEvent.setup();
    render(<ChannelChip channel={channel} />);
    expect(screen.queryByText(channel.description)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button'));
    expect(screen.getByText(channel.description)).toBeInTheDocument();
  });
});

describe('CitationList', () => {
  it('renders the no-event state rather than a bare answer', () => {
    render(<CitationList citations={[]} />);
    expect(screen.getByTestId('no-citations')).toHaveTextContent(
      copy.ask.noCitations,
    );
  });

  it('opens by default so the evidence is visible without a tap', () => {
    render(
      <CitationList
        citations={[{ label: 'Event: e1', kind: 'event', detail: 'Fed hikes' }]}
      />,
    );
    expect(screen.getByText('Event: e1')).toBeInTheDocument();
  });
});

describe('install prompt eligibility', () => {
  const now = Date.UTC(2026, 7, 15);
  const day = 24 * 3600 * 1000;

  it('never fires on a first session', () => {
    expect(eligible(1, 300, null, now)).toBe(false);
  });

  it('never fires before 60 seconds of use', () => {
    expect(eligible(3, 30, null, now)).toBe(false);
  });

  it('fires once both thresholds are met', () => {
    expect(eligible(2, 61, null, now)).toBe(true);
  });

  it('stays quiet for 30 days after a dismissal', () => {
    expect(eligible(5, 500, now - 10 * day, now)).toBe(false);
    expect(eligible(5, 500, now - 31 * day, now)).toBe(true);
  });
});
