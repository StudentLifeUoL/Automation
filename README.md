# automation

Personal scheduled checks and small automations, each self-contained in its
own folder so they can be added to or removed independently.

## journal-monitors/uad

Checks the "Üniversite Araştırmaları Dergisi" (UAD) journal page on
DergiPark (https://dergipark.org.tr/tr/pub/uad) every 10 hours via a GitHub
Actions workflow (`.github/workflows/uad-journal-monitor.yml`), looking for
signs that article submission has opened. Results are written to
`journal-monitors/uad/state.json`, committed only when the page content
changes. A separate scheduled Claude routine reads that file shortly after
each run and emails when submission looks like it has just opened.

The check runs on GitHub's own runners rather than from a Claude sandbox,
since sandbox environments here are network-restricted and can't reach
arbitrary external sites directly.
