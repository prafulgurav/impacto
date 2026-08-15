/**
 * Every user-facing string in the app.
 *
 * Nothing a user reads may be an inline literal in JSX. This file is the input to
 * the build-blocking compliance scan (lib/compliance), which runs the same
 * guardrail patterns the Python engine applies to generated text. Centralising
 * the copy is what makes that scan able to see all of it.
 *
 * Rules that shaped this wording:
 *   - no forward-looking claim about any named security or index
 *   - no buy / sell / hold language, and no phrasing that reads as an instruction
 *   - every statistic is described as historical and carries its sample size
 *   - the portfolio screen says EXPOSURE, never ACTION
 */

export const copy = {
  app: {
    name: 'Impacto',
    tagline: 'Global events, Indian market impact',
    description:
      'Impacto maps global events and policy decisions to Indian equity market impact, using an auditable transmission map and market-model event studies.',
  },

  nav: {
    today: 'Today',
    explore: 'Explore',
    ask: 'Ask',
    portfolio: 'Portfolio',
    more: 'More',
    calibration: 'Calibration',
    methodology: 'Methodology',
    compliance: 'Compliance',
    settings: 'Settings',
    skipToContent: 'Skip to content',
  },

  theme: {
    toggle: 'Change theme',
    light: 'Light',
    dark: 'Dark',
    system: 'Match system',
  },

  today: {
    title: 'Today',
    digestHeading: "Today's digest",
    alertsHeading: 'Active alerts',
    watchlistHeading: 'Your watchlist',
    empty:
      'No global event matching a tracked archetype was detected in the recent sessions.',
    emptyHint:
      'Moves you are seeing may be domestic, stock-specific, or flow-driven.',
    generatedAt: 'Generated',
    viewDetail: 'See the working',
  },

  explore: {
    title: 'Explore',
    subtitle:
      'Fifteen event archetypes, the channels they transmit through, and what happened to Indian equities the last time each one occurred.',
    familyHeading: 'Grouped by family',
    impactsHeading: 'Where it shows up',
    channelsHeading: 'How it transmits',
    distributionHeading: 'What happened last time',
    analogsHeading: 'Every past occurrence',
    rationaleHeading: 'Encoded reasoning',
    priorHeading: 'Encoded prior',
    realisedHeading: 'Realised outcome',
    noAnalogs:
      'There is no usable historical sample for this pairing yet, so the linkage rests on the economic mechanism alone.',
    windowLabel: 'Window',
    targetLabel: 'Target',
    seeTarget: 'Open the deep dive',
  },

  evidence: {
    sampleSize: 'n',
    pValue: 'p',
    noise: 'not distinguishable from noise',
    noiseExplainer:
      'Across this sample the distribution is not statistically distinguishable from zero, so treat the linkage as weak evidence.',
    hitRate: 'hit rate',
    median: 'Median',
    mean: 'Mean',
    range: '5th–95th percentile',
    spread: 'Spread',
    historical: 'Historical, across past occurrences of this archetype.',
    unitBps: 'bps',
    unitBpsFull: 'basis points',
  },

  charts: {
    impactBarsTitle: 'Encoded prior against realised median',
    impactBarsLegendBar: 'Bar: the range encoded in the transmission map',
    impactBarsLegendDot: 'Dot: the median that was actually realised',
    distributionTitle: 'Distribution of past outcomes',
    distributionMedianRule: 'Median',
    distributionZeroRule: 'No abnormal move',
    stripPlotHint: 'One dot per past occurrence.',
    axisCar: 'Cumulative abnormal return (bps)',
    noData: 'No sample to plot.',
  },

  ambiguity: {
    heading: 'This one cuts both ways',
    body:
      'The transmission map records this linkage as two-sided. The mechanism can transmit in either direction, and which way it goes depends on the specific cause of the event. The ambiguity is the finding, not a gap in it.',
  },

  ask: {
    title: 'Ask',
    placeholder: 'Why did IT stocks move?',
    submit: 'Ask',
    thinking: 'Composing from the evidence…',
    citationsHeading: 'What this is based on',
    noCitations:
      'No global event in the corpus explains this move. It may be domestic, stock-specific, or flow-driven.',
    aiDisclosure:
      'A language model rewrites statistics that were computed beforehand. It cannot introduce a number that is not in the evidence, and its output is checked before it is shown.',
    historyHeading: 'Earlier answers',
    historyDate: 'Answered on',
    suggestedHeading: 'From today’s detected events',
    errorHeading: 'That did not come back',
    errorBody: 'The answer could not be composed. Please try again.',
  },

  portfolio: {
    title: 'Portfolio exposure',
    subtitle:
      'Where your holdings sit relative to the sectors these archetypes have historically moved, and through which channels.',
    // Deliberate wording. This screen describes exposure and never action: no
    // "consider", no "you may want to", no red/green profit framing, and no
    // ranking that implies what to do about any of it.
    addHolding: 'Add a holding',
    symbolLabel: 'NSE symbol',
    weightLabel: 'Share of portfolio',
    symbolPlaceholder: 'Start typing a symbol',
    save: 'Save holdings',
    saved: 'Holdings saved',
    exposureHeading: 'Sector exposure',
    channelsHeading: 'Channels that reach these sectors',
    archetypesHeading: 'Archetypes that have historically moved them',
    emptyHeading: 'No holdings recorded',
    emptyBody:
      'Add the symbols you hold and their share of your portfolio to see which sectors that weight sits in.',
    weightsExceeded: 'Weights add up to more than the whole portfolio.',
    privacy:
      'Holdings are encrypted before they are stored, and every read of them is logged.',
    signInRequired: 'An account is needed to store holdings.',
  },

  auth: {
    signIn: 'Sign in',
    signOut: 'Sign out',
    google: 'Continue with Google',
    emailLabel: 'Email address',
    magicLink: 'Email me a sign-in link',
    magicLinkSent:
      'If that address has an account, a sign-in link is on its way. The link is valid for fifteen minutes.',
    whyHeading: 'Why an account',
    whyBody:
      'An account stores your watchlist, lets you receive notifications, and keeps your portfolio holdings.',
    withoutHeading: 'What works without one',
    withoutBody:
      'Browsing every archetype, every distribution, the calibration record and the explainer all work signed out. Nothing on the public side is gated.',
  },

  notifications: {
    enable: 'Notify me',
    prePermissionHeading: 'Before we ask your browser',
    prePermissionBody:
      'You would receive one pre-market digest on weekdays, plus alerts for high-severity events on your watchlist. Nothing else.',
    prePermissionFrequency: 'That is about five to seven notifications a week.',
    prePermissionContinue: 'Continue',
    prePermissionCancel: 'Not now',
    denied:
      'Notifications are blocked for this site in your browser settings. Your watchlist still works.',
    frequencyHeading: 'How often',
    frequencyDigest: 'Weekday pre-market digest',
    frequencyHigh: 'High-severity alerts only',
    frequencyAll: 'Every alert on my watchlist',
    contentNote:
      'A notification carries the event and its severity. It never carries a number.',
  },

  offline: {
    bannerOffline: 'You are offline.',
    bannerShowing: 'Showing data from',
    bannerStale: 'This data is from an earlier session.',
    retry: 'Try again',
    pageHeading: 'You are offline',
    pageBody:
      'This screen has not been saved to your device yet. Everything you have already opened is still available.',
    queuedHeading: 'Waiting to sync',
    queuedBody: 'Your changes are saved on this device and will sync when you reconnect.',
    syncedNow: 'Synced',
  },

  install: {
    heading: 'Add Impacto to your home screen',
    body: 'It opens faster and keeps working without a connection.',
    accept: 'Add',
    dismiss: 'Not now',
    iosHeading: 'Add to your home screen',
    iosBody:
      'In Safari, tap the Share button and then "Add to Home Screen". On iPhone, notifications only work once Impacto has been added this way.',
  },

  calibration: {
    title: 'Calibration',
    subtitle:
      'Every belief encoded in the transmission map, scored against what actually happened. Rules the data rejects are shown as rejected.',
    statusConfirmed: 'Confirmed',
    statusSignOk: 'Direction right, size off',
    statusContradicted: 'Contradicted',
    statusUnderpowered: 'Too few occurrences',
    statusNoData: 'No sample',
    confirmedHelp:
      'The realised median fell inside the range encoded in the map, with the encoded direction.',
    contradictedHelp:
      'The realised median moved against the direction encoded in the map.',
    underpoweredHelp:
      'There are fewer past occurrences than this archetype requires before its statistics mean anything.',
    lastRun: 'Last scored',
  },

  methodology: {
    title: 'Methodology',
    heading: 'How the numbers are produced',
    body:
      'Each past occurrence of an archetype is run through a market-model event study. A regression over a 120-session estimation window, ending 10 sessions before the event, gives the expected return for a target. The abnormal return is the difference between what the target did and what that model expected, and the cumulative abnormal return sums those differences across the event window.',
    windowsHeading: 'What the windows mean',
    windowsBody:
      'T+0 is the session of the event itself. T+1..T+5 covers the five sessions after it. A wider window captures more of a slow-transmitting channel and also more unrelated noise.',
    distributionHeading: 'Why a distribution and not a forecast',
    distributionBody:
      'A distribution of past outcomes is a statement of historical fact. A single expected figure for a named security would be a recommendation, which is a regulated activity. The spread is also the honest answer: these samples are small and the variance is wide.',
    limitsHeading: 'What this cannot tell you',
    limitsBody:
      'Samples are small, often fewer than twenty occurrences. Market structure changes. Two events of the same archetype can differ in ways the classifier cannot see. Where a distribution is not distinguishable from noise, the interface says so.',
  },

  compliance: {
    title: 'Compliance',
    sebiHeading: 'Position under SEBI regulations',
    sebiBody:
      'Impacto is not registered with SEBI as a Research Analyst or an Investment Adviser, and it does not carry on either activity. It publishes historical statistics and descriptions of economic mechanisms, for information and education.',
    isHeading: 'What this is',
    isBody:
      'A record of what Indian equity sectors did after past occurrences of a set of global event archetypes, with the reasoning that links the two, and a calibration record showing where that reasoning has held up.',
    isNotHeading: 'What this is not',
    isNotBody:
      'It is not investment advice, not a research recommendation, and it makes no claim about future prices. Past abnormal returns do not predict future returns.',
    aiHeading: 'Use of AI',
    aiBody:
      'A language model is used only to rewrite statistics that were already computed. It is given the retrieved evidence and nothing else, it cannot introduce a figure, and its output is checked against the same rules as the rest of the interface before it is shown. Every answer that is shown is recorded.',
    sourcesHeading: 'Data sources',
    sourcesBody:
      'Price data from the configured market provider. Event detection from GDELT and public Indian financial news feeds. The transmission map is maintained in this repository and is open to inspection.',
    contactHeading: 'Questions',
    contactBody:
      'Consult a SEBI-registered investment adviser before making any investment decision.',
  },

  settings: {
    title: 'Settings',
    themeHeading: 'Appearance',
    watchlistHeading: 'Watchlist',
    notificationsHeading: 'Notifications',
    offlineHeading: 'Offline data',
    lastSync: 'Last synced',
    storageUsed: 'Saved on this device',
    clearData: 'Clear saved data',
    accountHeading: 'Account',
  },

  disclaimer: {
    short:
      'Historical statistics for information only. Not investment advice.',
    full:
      'Impacto presents historical statistics and economic mechanisms for information and education only. It is not investment advice, not a research recommendation, and makes no claim about future prices. Past abnormal returns do not predict future returns. Consult a SEBI-registered investment adviser before making any investment decision.',
  },

  errors: {
    generic: 'Something did not load.',
    retry: 'Try again',
    notFound: 'That page does not exist.',
    notFoundBody: 'The link may be out of date.',
    offline: 'This needs a connection and you are offline.',
    rateLimited: 'Too many requests just now. Please wait a moment.',
  },

  a11y: {
    loading: 'Loading',
    chartDescription: 'Chart. The same figures are listed in the table below.',
    externalLink: 'Opens in a new tab',
    expand: 'Show more',
    collapse: 'Show less',
  },
} as const;

export type Copy = typeof copy;
export default copy;
