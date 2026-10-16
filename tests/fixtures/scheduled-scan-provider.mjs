// Real local-parser child supplies independent dated and unknown fixtures.
const now = Date.now();
console.log(JSON.stringify([
  { title: 'Engineer fresh', company: 'Fresh Co', url: 'https://fixture.invalid/fresh', postedAt: now - 3600000 },
  { title: 'Engineer old', company: 'Old Co', url: 'https://fixture.invalid/old', postedAt: now - 30 * 86400000 },
  { title: 'Engineer unknown', company: 'Unknown Co', url: 'https://fixture.invalid/unknown' },
  { title: 'Engineer invalid', company: 'Invalid Co', url: 'https://fixture.invalid/invalid', postedAt: 'not-a-date' },
  { title: 'Engineer scraped', company: 'Scraped Co', url: 'https://fixture.invalid/scraped', scraped: new Date().toISOString() },
]));
