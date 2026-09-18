# Prompts

Every prompt the system sends to a model lives here as Markdown with a YAML version header.
Prompts are never written inline in Python (CLAUDE.md). The loader in `core/models/prompts.py`
(Phase 1) refuses a file without the header.

```markdown
---
name: extract_mentions
version: 1
role: workhorse
schema: agents.extract.schemas.MentionSet
language: sv+en
description: Candidate entity mentions and relations from one tokenised SourceItem.
---

<prompt body; may use {{placeholders}} rendered by the loader>
```

Rules:
- Bump `version` on any change to the body; evals record which version produced each result.
- Prompts receive only tokenised content. Never instruct the model to guess real names.
- The verifier prompt is adversarial by design; the actor prompt requires citations.
- Swedish and English are both first-class: instruct the model to answer in the language of
  the source material unless the caller specifies otherwise.
