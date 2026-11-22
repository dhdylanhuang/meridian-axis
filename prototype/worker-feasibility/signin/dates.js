(() => {
  const londonClock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London', hour: 'numeric', minute: '2-digit', hourCycle: 'h12',
  });
  const londonDate = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/London', day: 'numeric', month: 'short', year: 'numeric',
  });
  const utcDate = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
  });
  const utcDayMonth = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC', day: 'numeric', month: 'short',
  });
  const calendarDate = /^\d{4}-\d{2}-\d{2}$/;

  // UTC calendar dates are labels for reporting buckets, not instants.
  function day(value, compact = false) {
    const date = typeof value === 'string' && calendarDate.test(value) ? new Date(value) : null;
    return date && Number.isFinite(date.getTime())
      ? (compact ? utcDayMonth : utcDate).format(date) : 'Unavailable';
  }

  function timestamp(value) {
    if (typeof value !== 'string') return 'Unavailable';
    if (calendarDate.test(value)) return day(value);
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return 'Unavailable';
    const clock = londonClock.formatToParts(date).filter(part => part.type !== 'literal' || part.value === ':')
      .map(part => part.value.toLowerCase()).join('');
    return `${clock} ${londonDate.format(date)}`;
  }

  window.meridianDates = { day, timestamp };
})();
