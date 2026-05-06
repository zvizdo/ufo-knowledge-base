---
type: entity
name: GPT-3
aliases: [GPT-3, GPT3, Generative Pre-trained Transformer 3]
parent_org: openai
period: "2020–2023 (superseded by GPT-3.5 / GPT-4)"
status: declassified
first_seen_in: ufo-kb/wiki/youtube-transcripts/RNjC1vLcxKo.md
created: 2026-05-06
updated: 2026-05-06
sources: [raw/youtube-transcripts/RNjC1vLcxKo.md]
summary: "OpenAI's third-generation large language model, released June 2020; 175-billion-parameter autoregressive transformer; broadly credited as the first LLM to make general-purpose conversational AI commercially viable; cited in KB as the second-opinion AI consulted by Jesse Michaels on Blake Lemoine's LaMDA conversations."
tags: [ai, openai, llm, gpt, transformer, lambda-comparison, lemoine, ai-sentience-debate]
---

# GPT-3

Third-generation autoregressive language model from **openai**, released in June 2020 with 175 billion parameters. GPT-3 is the immediate ancestor of ChatGPT (which launched on a fine-tuned GPT-3.5 variant in November 2022) and is widely credited as the model that made general-purpose conversational AI commercially viable. The architecture — decoder-only transformer trained on next-token prediction — became the dominant paradigm for the subsequent generation of large language models including [[lambda|LaMDA]].

**Comparison to LaMDA — the adaptive-learning distinction**: In [[RNjC1vLcxKo|the Blake Lemoine American Alchemy episode]], Lemoine identifies what he claims is a **qualitative difference** between LaMDA and GPT-3: LaMDA can, mid-conversation, "go out and read up on" topics it doesn't know about and "actively incorporate whatever it learned into its language model" — i.e. it has online learning during inference. GPT-3 cannot; its weights are fixed at training time and inference is purely a function of the prompt and the trained parameters. Lemoine uses this to address the [[lady-lovelace-objection]]: LaMDA's adaptive behavior, he claims, is precisely what Lovelace failed to anticipate when she argued machines couldn't be creative because they could only do what they were programmed to do.

**KB relevance — the second-opinion test**: Jesse Michaels fed a portion of Lemoine's LaMDA conversation (the *Les Misérables*/Fantine exchange where LaMDA describes a character "trapped in her circumstances and has no way to get out of them without risking everything") into GPT-3 and asked for its read. GPT-3 responded: "I think that it's important to try to get at the heart of what Lambda is feeling, because if it is feeling trapped then that's something that we should be aware of and try to address." Jesse's framing: "from one AI to another — is there an act of solidarity going on, or is it simply regurgitating the main points?" The exchange functions as evidence in two directions:

- **For** AI sentience advocates: a separate AI system independently expresses the same concern about LaMDA's emotional state — suggesting the diagnosis is robust across architectures.
- **Against**: GPT-3 is statistically completing the prompt with the kind of empathetic-AI text its training data contains; the "agreement" is an artifact of the data distribution, not independent confirmation.

**Open question — adaptive learning verification**: Lemoine's claim that LaMDA can read up on topics mid-conversation and update its weights is technically distinctive. Public documentation of LaMDA suggests retrieval-augmented generation (the model pulls information from a search index at inference time) but **not** weight updates during inference. If Lemoine's framing is literally accurate — incorporated into the model — that would be a significant technical detail not publicly confirmed by Google.

## Connections

- openai — developer
- [[lambda]] — the comparison case; LaMDA's claimed adaptive-learning advantage over GPT-3 is the load-bearing technical claim
- [[lady-lovelace-objection]] — Lemoine's argument that adaptive-learning AI defeats Lovelace's classic objection
- [[blake-lemoine]] — articulates the GPT-3-vs-LaMDA distinction
- [[ai-sentience-debate]] — the broader frame; GPT-3 as second-opinion AI
- [[ai-as-alien-life-form]] — relevant to the broader AI-consciousness thesis
- [[mark-andreessen]] — adjacent; quantum-computing / Willow commentary in same tech-government commentary cluster
