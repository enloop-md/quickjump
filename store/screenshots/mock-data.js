// Mocked jumps for the store screenshots and the website. Not real data.
const fav = (name) => new URL(`favicons/${name}.svg`, import.meta.url).href;

export const JUMPS = [
  { id: 'j1', tabId: 11, title: 'Very important call', url: 'https://meet.example.com/abc-defg-hij', favIconUrl: fav('call'), profile: 'WORK' },
  { id: 'j2', tabId: 12, title: 'Q4 roadmap — draft', url: 'https://docs.example.com/q4-roadmap', favIconUrl: fav('doc'), profile: 'WORK' },
  { id: 'j3', tabId: 13, title: 'Production dashboard', url: 'https://metrics.example.com/prod', favIconUrl: fav('dash'), profile: 'WORK' },
  { id: 'j4', tabId: 14, title: 'PR #1287: Fix login timeout', url: 'https://git.example.com/app/pull/1287', favIconUrl: fav('pr'), profile: 'WORK' },
  { id: 'j5', tabId: 15, title: 'Team chat — #release', url: 'https://chat.example.com/release', favIconUrl: fav('chat'), profile: 'WORK' },
  { id: 'j6', tabId: 21, title: 'Flight check-in', url: 'https://air.example.com/checkin', favIconUrl: fav('plane'), profile: 'Personal' },
  { id: 'j7', tabId: null, title: 'Inbox (3)', url: 'https://mail.example.com/', favIconUrl: fav('mail'), profile: 'Personal' },
];
