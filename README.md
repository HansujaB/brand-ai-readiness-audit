# Brand AI readiness audit

**For use by an AI agent only.** This submission is an Agent Skill Marketplace in the standard Agent Skills format. The agent reads the designated entrypoint's `SKILL.md`, follows its procedure and delivers the final audit report. Bundled Python scripts support collection and automatic checks; executing them alone does not perform the agent's required evidence review.

## Use the skill

Keep the entire marketplace together in the agent's workspace, including `marketplace.json`, `skills/` and the shared `auditlib/` package. The agent needs file access, Python execution and public website access. Ask the agent:

> Read `skills/audit-orchestrator/SKILL.md` and use this skill marketplace to audit https://example.com. Follow the specialist instructions, review the evidence and deliver only the final company report.

You may include a company name, country and language in the request. Otherwise the agent resolves one country/language version from the URL and the website's published information. It does not assume India; a site with no country information still works as one default/global version.

## How the entrypoint composes the skills

`marketplace.json` lists four skills and marks exactly one entrypoint: `audit-orchestrator`.

| Skill | Responsibility |
|---|---|
| [audit-orchestrator](skills/audit-orchestrator/SKILL.md) | Establish scope and deadline, compose specialist checks, review evidence, consolidate findings and validate the final report |
| [crawl-render-audit](skills/crawl-render-audit/SKILL.md) | Assess crawler/index access, metadata, internal discovery, raw/rendered content, media and structured data |
| [freshness-corroboration](skills/freshness-corroboration/SKILL.md) | Assess fact qualifications, same-site policy/price consistency, dates and business identity |
| [engagement-audit](skills/engagement-audit/SKILL.md) | Assess visitor questions, information paths and desktop/mobile obstacles |

The agent reads the specialist procedures and uses their shared Python runner once to collect evidence and apply automatic checks. It then reviews uncertainty, makes any targeted follow-ups within the original deadline, groups repeated problems and validates the same report file. The entrypoint instructions contain the helper commands and review criteria.

## Agent environment setup

Prepare these dependencies in the environment where the agent executes its tools. These commands install dependencies; they do not invoke the skill.

```sh
python -m pip install -r requirements.txt
```

Browser and PDF support are optional:

```sh
python -m pip install -r requirements-optional.txt
python -m playwright install chromium
```

When browser evidence is unavailable, the agent records any material limitation in the report.

## Report and scope

The agent delivers only `<company>_report.json`, such as `ikea_report.json` or `lifestyle_report.json`. The business report contains severity counts, short evidence and specific prioritized fixes with verification steps. Improvements have separate counts. Repeated fixes are grouped, with at most eight priority findings, three improvements and three example links per finding. A brief note identifies material limitations or additional confirmed findings omitted from the short report. See the [input and report contract](skills/audit-orchestrator/references/schema.md).

Every request stays on the supplied URL's exact origin, including assets and redirects. The audit covers one country and language, respects robots.txt and remains read-only. It fetches no outside sources and performs no authenticated or transactional actions. It assesses website-controlled discoverability and engagement signals; it does not measure actual assistant citations or rankings.

There is one full audit workflow. Collection, agent review and final validation share a five-minute deadline; the skill normally allocates 210 seconds to the helper runner and reserves the remainder for review. Detailed evidence stays internal, with no diagnostic files delivered.