# Chapter 6 — Question Parsing: Structure Before Searching

The previous chapter argued that documents must be parsed into structured form before anything useful can happen — that everything lost in parsing cannot be recovered later. This chapter makes the same argument about questions.

A question is also an unstructured input. The user types a string. That string carries intent, scope, expected answer shape, possibly several sub-questions, possibly references to specific document regions, possibly assumptions about what the system can and can't do. None of this is visible to retrieval if the question is treated as a flat string. A retrieval engine that takes "What is the maximum coverage and what are the exclusions?" as a single search query will return passages that mix the two topics, and the LLM downstream will produce a confused answer that loses one of them.

The fix is structural, not algorithmic. The question gets parsed into a structured object — exactly as the document does in Chapter 5. Out of that parsing comes everything the rest of the pipeline needs: the intent, the keywords, the scope filters, the decomposition pattern if there is one, the expected answer shape, the sub-functions to activate, the sub-functions to skip. The remainder of the system reads this structured object and acts on it; it never re-parses the raw question.

This chapter develops question parsing as the second pillar of any RAG system, the symmetric counterpart of document parsing. The same philosophy holds for both: **structure before search**. Whatever signal the question carries that the system needs, extract it explicitly into a typed field. Whatever the question implies about what the system should do, capture it as an activation flag. Whatever the question doesn't say but the document type makes obvious, fill it in based on context.

The chapter has another job: it formalizes the function `ask_document(question, document)` introduced in Chapter 1. This is the public API of the system for Parts I-III; Chapter 6 develops its arguments, its output schema, and the philosophy that connects them. The single-function contract is what makes the four bricks composable; question parsing is what makes that single function usable.

## 1. The symmetry with document parsing

Chapter 5 made the case for parsing documents into structured DataFrames — `line_df`, `chunk_df`, `toc_df`, `image_df`. The question is the system's other input. It deserves the same treatment.

The parallel is not metaphorical. It's structural:

| Chapter 5 (document parsing) | Chapter 6 (question parsing) |
|---|---|
| Input: PDF / Word / image | Input: user question (string) |
| Output: structured DataFrames | Output: structured Pydantic object |
| Job: transform unstructured → structured | Job: transform unstructured → structured |
| Lost in parsing = lost forever | Lost in parsing = lost forever |
| Downstream consumers read the structures | Downstream consumers read the parsed question |

The two bricks are the **input pair** of the four-brick architecture from the Part II opener. Both produce typed structures that the retrieval brick (Chapter 7) and the generation brick (Chapter 8) consume. Both are silent failure modes when done badly: a document parsed into noise produces noisy retrieval; a question parsed shallowly produces shallow retrieval. Both require investment proportional to the complexity of what they handle.

A note on terminology. The standard term in the RAG literature is "query understanding" or "question understanding." Both are acceptable, but they're passive — they suggest the system *comprehends* the question, which is vague. We prefer **question parsing** for the same reason document specialists prefer "PDF parsing" over "PDF understanding": the active verb names what the system actually does (transform structure A into structure B), not the cognitive analogy.

The chapter title carries this: *Question Parsing: Structure Before Searching*, mirroring Chapter 5's *Parsing: Structure Before Search*. The two-letter difference in the subtitle is intentional. Chapter 5 prepares the document so search can happen; Chapter 6 prepares the question so search can happen on the right things.

## 2. The function as facade

Before going into what question parsing produces, it helps to recall what the whole system looks like from the outside.

Chapter 1 introduced the public API as a single function:

```python
result = ask_document(
    question="What is the premium amount?",
    document=contract_pdf,
)
```

The user passes a question and a document. They get back a structured JSON answer. That's the whole API surface. Whatever happens inside — parsing, question parsing, retrieval, generation, feedback loops, dispatcher decisions — is implementation detail.

Chapter 1 also previewed that the same shape generalizes to corpus scale:

```python
result = ask_corpus(
    question="How many active P&C contracts mention liability caps above €1M?",
    corpus=broker_corpus,
)
```

Two sister functions, same contract, scope explicit in the name. `ask_document` is the focus of Parts I-III; `ask_corpus` is developed in Part IV.

The reason this matters here is that **question parsing produces the input that drives the rest of `ask_document`**. Everything the dispatcher will activate, everything retrieval will search for, everything generation will format — all of it is determined by what question parsing returns. If question parsing returns shallow output, the rest of the pipeline operates blindly. If it returns rich, structured output, the rest of the pipeline can be deliberate about what it does.

In practice, `ask_document` is implemented roughly like this:

```python
def ask_document(
    question: str,
    document,
    **overrides,
) -> dict:
    # Brick 1 — document parsing (Chapter 5)
    doc_struct = parse_document(document)
    # Brick 2 — question parsing (this chapter)
    parsed_q = parse_question(question, doc_profile=profile_of(doc_struct), **overrides)
    # Brick 3 — retrieval (Chapter 7)
    filtered = retrieve(doc_struct, parsed_q)
    # Brick 4 — generation (Chapter 8)
    answer = generate(parsed_q, filtered)
    # Final assembly with metadata
    return assemble(answer, parsed_q, _meta=trace_of(parsed_q, filtered, answer))
```

Five lines of orchestration. Each brick has its own chapter. This chapter is about `parse_question`. Everything else is named for context but developed elsewhere.

## 3. What question parsing produces

The output of question parsing is a Pydantic object. Let's build it up progressively, starting from the minimum and adding the fields the rest of the book uses.

### The minimal version

At its simplest, parsing extracts what the question is about and what kind of answer it expects:

```python
class ParsedQuestion(BaseModel):
    original_question: str
    intent: Literal["qa", "summarization", "translation"]
    keywords: list[str]
    expected_answer_shape: str  # "amount", "date", "list", "boolean", "text"
```

For the question "What is the premium amount?", this might produce:

```python
ParsedQuestion(
    original_question="What is the premium amount?",
    intent="qa",
    keywords=["premium", "amount"],
    expected_answer_shape="amount",
)
```

This already does work for the rest of the pipeline. Retrieval knows to search for "premium" and "amount". Generation knows the answer should look like a monetary amount, not a paragraph of prose. The four downstream bricks have a typed contract instead of a string.

But this minimal version misses most of what makes question parsing valuable.

### Adding the execution plan

The question carries information about *what should happen*, not just *what to look for*. Different questions activate different sub-functions in the pipeline.

A point lookup like "What is the effective date?" needs simple keyword retrieval and a single LLM call. A listing question like "What are all the obligations of the seller?" needs exhaustive coverage of the obligations sections and a different generation strategy (Chapter 12). A comparison question like "How does the 2024 version differ from 2023?" needs to operate on multiple documents (Tome 2). The system has to *decide* which sub-functions to activate.

The decision lives in the parsed question:

```python
class ExecutionPlan(BaseModel):
    use_toc_navigation: bool = True
    use_keyword_retrieval: bool = True
    use_embeddings: bool = False  # fallback only, see Chapter 7
    follow_cross_references: bool = False
    decompose_compound: bool = False
    iterate_on_feedback: bool = True
    max_iterations: int = 3
    extract_page_numbers: bool = True
    extract_line_numbers: bool = True
class ParsedQuestion(BaseModel):
    # Fields from the minimal version
    original_question: str
    intent: Literal["qa", "summarization", "translation"]
    keywords: list[str]
    expected_answer_shape: str
    # The execution plan
    activations: ExecutionPlan
```

Now the parsed question doesn't just describe the question — it tells the system what to do. The rest of the pipeline reads `activations` and behaves accordingly.

### Adding scope filters

Some questions narrow the scope explicitly: "in the warranty section", "before March 2024", "for clients in France". These are scope filters that retrieval should apply *before* searching for the keywords.

```python
class ScopeFilters(BaseModel):
    sections: list[str] = Field(default_factory=list)
    date_range: tuple[str, str] | None = None
    parties: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    page_range: tuple[int, int] | None = None
    custom: dict = Field(default_factory=dict)
```

For "What does the warranty section say about liability before 2024?":

```python
scope = ScopeFilters(
    sections=["warranty"],
    date_range=("0001-01-01", "2023-12-31"),
)
```

At single-document scale, these filters constrain *where in the document* retrieval looks. At corpus scale (Part IV), they become SQL clauses on the corpus index. Same conceptual object, different physical execution. This continuity is part of why scoping belongs in the parsed question rather than as separate retrieval parameters.

### Adding decomposition

When the question is compound — "What is the premium and what are the exclusions?" — it needs to be decomposed before processing. Chapter 6 distinguishes four decomposition patterns:

- **Independent**: two unrelated facts, processed in parallel
- **Sequential**: q2 depends on q1, processed in order
- **Unified**: same conceptual question phrased with two terms, no decomposition
- **Conditional**: a condition narrows the scope of the actual question

The parsed question carries this:

```python
class Decomposition(BaseModel):
    pattern: Literal["single", "independent", "sequential", "unified", "conditional"] = "single"
    sub_questions: list[str] = Field(default_factory=list)
    conditional_filter: dict | None = None
```

For "What is the premium and what are the exclusions?":

```python
Decomposition(
    pattern="independent",
    sub_questions=[
        "What is the premium?",
        "What are the exclusions?",
    ],
)
```

For "Which insurer provides the most coverage in our P&C portfolio?":

```python
Decomposition(pattern="single")  # not actually compound, despite "and"-like surface
```

The decomposition pattern determines whether `ask_document` runs once or several times, in parallel or sequentially, with what coordination. We come back to decomposition in Section 7.

### The full schema

Putting it together:

```python
class ParsedQuestion(BaseModel):
    # The raw input, kept for audit
    original_question: str
    # What the user is asking
    intent: Literal["qa", "summarization", "translation"]
    keywords: list[Keyword]
    expected_answer_shape: str
    # How the question is structured
    decomposition: Decomposition
    scope_filters: ScopeFilters
    # What the system should do
    activations: ExecutionPlan
    # What the system should remember about its own choices
    parsing_notes: list[str] = Field(default_factory=list)
    suggested_clarification: str | None = None
```

The `parsing_notes` field captures things the parser noticed but didn't enforce — "user mentioned 'page 5' but document is Word format, page numbers approximate", "compound question detected, decomposed into 2 sub-questions". These notes flow through to the answer's `_meta` block (Chapter 8) so the user can see what the system inferred.

The `suggested_clarification` field is set when the question is ambiguous enough that the system would rather ask back than guess. We address this in Section 9.

This is the schema. The rest of the chapter is about how it gets filled.

## 4. Three intents, three pipelines

The first decision question parsing makes is the intent. Every question falls into one of three families, and each routes to a different downstream pipeline.

**QA (question answering).** The user wants a specific piece of information from the document. This is the default and the most common case. "What is the premium?" "Who are the parties?" "When does the coverage start?" Retrieval focuses on finding the passages that contain the answer; generation extracts and cites.

**Summarization.** The user wants the system to produce a synthesis of some scope. "Summarize the exclusions section." "Give me an executive summary of this contract." "Summarize chapter 3." Retrieval is exhaustive within the requested scope (no top-k tricks); generation works through the scope linearly to produce coherent prose.

**Translation.** The user wants content of the document rendered in another language. "Translate the warranty clause to French." "Render this section in plain English." Retrieval identifies the passage to translate; generation handles the language-to-language rendering, ideally preserving structure (lists, tables, citations).

Why these three? Because the operational pipelines for each are genuinely different:

| Intent | Retrieval strategy | Generation strategy | Output shape |
|---|---|---|---|
| QA | Find specific passages, top-k | Extract and cite | Structured answer with citations |
| Summarization | Exhaustive within scope | Linear pass, hierarchical merge | Prose summary with section coverage |
| Translation | Identify passage to render | Language-to-language with structure preservation | Rendered passage in target language |

A pipeline tuned for QA on a question that's actually summarization will return a fragment instead of a synthesis. A pipeline tuned for summarization on a QA question will return a verbose paragraph when a single value was wanted. The intent classification at parsing time prevents both.

Detection in practice is mostly surface-level pattern matching:

- "Summarize", "give me an overview of", "what does this say about" → summarization
- "Translate", "in French", "in plain English", "render as" → translation
- Everything else → QA (the default)

For ambiguous cases, the LLM is asked to classify. The cost is one cheap call; the benefit is correct routing for the entire downstream pipeline.

This intent field is what allows `ask_document` to specialize without exposing three separate functions. The user calls `ask_document(question, document)` regardless of intent; the parser handles routing internally.

## 5. Keyword extraction from three sources

Once the intent is set, the parser extracts keywords. These drive retrieval (Chapter 7). They are not the question — they are the search signals derived from the question.

Keywords come from three sources, which is more than most teams realize.

**Direct extraction from the question.** The simplest source: nouns, verbs, named entities, and quoted strings from the question text. "What is the premium amount in the policy?" gives `["premium", "amount", "policy"]`. This is what naive systems do, and it works for many easy questions. It fails when the question and the document use different vocabulary.

**LLM-suggested expansion.** The LLM is asked: "What other words might this concept be expressed as in a document?" For "premium," the expansion might include `["fee", "rate", "cost", "annual payment"]`. This catches paraphrase. It's the mechanism behind HyDE (Hypothetical Document Embeddings), reframed: HyDE generates a fake answer and embeds it; here we generate likely keywords directly. The cost is one LLM call; the benefit is keyword robustness across phrasing differences.

**Expert-provided keywords.** The most underused source, and often the most valuable in enterprise contexts. Domain experts know the meaningful synonyms in their field. In insurance, "premium" might map to internal terms like "prime", "cotisation", "tarif annuel" — none of which an LLM would generate from the English word "premium" alone. In legal documents, "non-compete clause" might appear as "restrictive covenant", "post-employment restraint", or jurisdiction-specific terms. In medical contexts, abbreviations and Latin terms multiply quickly.

Expert-provided keywords live in a maintained dictionary, organized by question type or by document type:

```python
EXPERT_KEYWORDS = {
    "premium": {
        "primary": ["premium", "prime", "annual_premium"],
        "synonyms": ["fee", "cotisation", "tarif", "cost"],
        "regex": [r"\bprime?\s+(?:annuelle|d'assurance)\b"],
        "associated_units": ["EUR", "€", "USD", "$"],
    },
    "non_compete": {
        "primary": ["non-compete", "non-competition"],
        "synonyms": ["restrictive covenant", "post-employment restraint"],
        "regex": [r"\bnon[-\s]compet(?:e|ition)\b"],
    },
}
```

When the parser identifies "premium" in the user's question, it pulls in the expert dictionary entry. Retrieval then searches for all variants, weighted appropriately. The dictionary grows with the project — every time the team identifies a missed retrieval that turned out to be a vocabulary mismatch, a new entry or a new variant is added.

The three sources combine in the parsed output:

```python
class Keyword(BaseModel):
    text: str
    weight: float = 1.0
    source: Literal["direct", "llm_expansion", "expert_dictionary"]
    semantic_group: str | None = None
    is_regex: bool = False
```

A typical output for "What is the premium amount?":

```python
keywords = [
    Keyword(text="premium",     weight=1.0, source="direct"),
    Keyword(text="amount",      weight=0.8, source="direct"),
    Keyword(text="prime",       weight=1.0, source="expert_dictionary", semantic_group="premium"),
    Keyword(text="cotisation",  weight=0.9, source="expert_dictionary", semantic_group="premium"),
    Keyword(text=r"\bprime?\s+annuelle\b", weight=1.0, source="expert_dictionary", is_regex=True),
    Keyword(text="fee",         weight=0.6, source="llm_expansion"),
    Keyword(text="rate",        weight=0.5, source="llm_expansion"),
]
```

The retrieval brick (Chapter 7) reads this list and uses the weights, semantic groups, and regex flags to construct its actual search. Question parsing doesn't search; it produces the search signals.

A note on why this matters. Standard RAG tutorials assume that embedding similarity will handle synonyms automatically. For some domains, it does — embeddings of "doctor" and "physician" land close in vector space because the training data treated them similarly. For specialized enterprise vocabulary, it doesn't. Embedding models have rarely seen "DDPE" (a French insurance acronym), "GAV" (another), or jurisdiction-specific legal terms. The expert dictionary fills this gap explicitly, which is more reliable than hoping the embeddings will figure it out.

We come back to the keyword strategies in Chapter 7, which uses them. Here, they're an output of parsing.

## 6. Document-aware activations

A subtle but important point: the parsed question depends not only on the question itself but on the document it will be applied to. Some activations make sense for one document type and not another.

The clearest example: page numbers in PDF vs Word documents.

A user asks "What does it say on page 1?" If the document is a PDF, "page 1" is well-defined — pages are physical artifacts of the format, the parser knows their boundaries, retrieval can target page 1 directly. The activation `extract_page_numbers=True` is sensible.

If the document is a Word file, "page 1" is ill-defined. Pagination in Word depends on the renderer — the user's font preferences, the screen width, the print driver. The "page 1" the user saw on their screen may be different from "page 1" in another viewer. The activation `extract_page_numbers=True` is misleading at best, harmful at worst (the system might confidently cite "page 2" when the user's question was about a different "page 2").

The right behavior is for question parsing to look at the document's profile (metadata from Chapter 5's parsing) and adjust the activations accordingly:

```python
def parse_question(question: str, doc_profile: DocumentProfile) -> ParsedQuestion:
    parsed = base_parse(question)
    if doc_profile.format == "docx":
        # Pages are renderer-dependent; downgrade to "approximate location"
        parsed.activations.extract_page_numbers = False
        parsed.parsing_notes.append(
            "User mentioned page numbers, but document is Word format. "
            "Page references will be approximate."
        )
    if doc_profile.format == "html":
        # No pagination at all
        parsed.activations.extract_page_numbers = False
    if not doc_profile.has_toc:
        # TOC navigation isn't possible
        parsed.activations.use_toc_navigation = False
    return parsed
```

This is more than a defensive check. It's a way to make the system honest with the user. The `parsing_notes` flow into the answer's `_meta` block, so the user knows the system understood the limitation. They don't get a confidently wrong "page 2" answer; they get an answer with a note that page references are approximate in this format.

The same logic generalizes to other document properties:

| User asks about... | If document doesn't support it... |
|---|---|
| Page numbers | Word, HTML, plain text → downgrade or skip |
| Section headings | Documents without declared TOC → use heuristics or skip |
| Tables | Documents without parseable tables → flag |
| Cross-references | Documents without resolvable references → skip following them |
| Time validity | Static documents (no version metadata) → ignore time-based filters |

Each of these is a small adjustment, but together they make the difference between a system that gives a clean answer with appropriate caveats and a system that fabricates structure that isn't there.

> **Common pitfall** — Hard-coding the activation flags as defaults regardless of document type. A pipeline that always sets `extract_page_numbers=True` produces page citations even when the underlying document type doesn't have meaningful pages. Users who notice the inconsistency lose trust; users who don't notice get misleading citations. The activations must be derived from the document's actual properties, not from project-wide defaults.

## 7. Compound question decomposition

Many user questions are compound — they look like one question but actually pack two or more. "What is the premium and what are the exclusions?" "Who is the insured party, and what is their address?" "If the policy is for commercial property, what is the fire coverage limit?"

Treating these as a single search query produces bad answers. Retrieval that searches for "premium AND exclusions" returns passages that mention both, which is rare and often unhelpful. Generation that tries to extract "the answer" from a compound question often returns one part and silently drops the other.

The fix is to detect compound questions at parsing time and decompose them. Four patterns recur often enough to deserve explicit names:

**Independent.** Two unrelated facts joined by "and": "What is the premium and what are the exclusions?" The two parts have nothing to do with each other; they retrieve different passages, generate independent answers, get assembled in the output. The system runs `ask_document` twice in parallel and merges.

**Sequential.** The second part depends on the first: "Who is the insured party, and what is their address?" The address is *of the insured party* — you have to identify the party first, then look up their address. The system runs the first sub-question, uses its answer to refine the second, then runs the second.

**Unified.** Two terms that refer to the same concept, not actually two questions: "What are the exclusions and limitations?" In most policy documents, "exclusions" and "limitations" appear together in the same section and refer to overlapping content. Decomposing this into two sub-questions duplicates work. The right treatment is to keep it as one question with both terms boosted in keyword retrieval.

**Conditional.** A condition narrows the scope of the actual question: "If the policy is for commercial property, what is the fire coverage limit?" The condition becomes a scope filter; the actual question is "what is the fire coverage limit", run on the subset of the document that matches the condition.

How does the parser tell which pattern applies?

The "and" disambiguation test: **if you replace "and" with "; also", does it still read naturally?**

- "What is the premium **and** what are the exclusions?" → "What is the premium**; also,** what are the exclusions?" reads naturally → **Independent**.
- "What are the exclusions **and** limitations?" → "What are the exclusions**; also,** limitations?" reads awkwardly → **Unified**.
- "Who is the insured **and** their address?" → also reads naturally as two distinct asks → **Independent or Sequential**, distinguished by whether the second depends on the first.
- "If X, what is Y?" → conditional surface form → **Conditional**.

For the harder cases, the LLM is asked to classify:

```python
class Decomposition(BaseModel):
    pattern: Literal["single", "independent", "sequential", "unified", "conditional"]
    sub_questions: list[str] = Field(default_factory=list)
    conditional_filter: dict | None = None
    coordination_notes: str | None = None
def decompose(question: str) -> Decomposition:
    # Heuristic first
    if not has_compound_indicators(question):
        return Decomposition(pattern="single")
    # LLM if heuristic flags possible decomposition
    return llm_classify_decomposition(question)
```

Once the decomposition is known, the orchestrator handles the rest. For Independent, two parallel runs of `ask_document` whose results are joined. For Sequential, two sequential runs. For Unified, no decomposition. For Conditional, one run with the condition translated into scope filters.

Decomposition is one of the most cost-effective question parsing decisions in production. It's the difference between a system that handles compound questions gracefully and one that drops half the answer. We come back to the actual coordination logic in Chapter 13 (feedback loops) and Chapter 15 (composite pipeline).

> **In the wild** — A team building a contract-review system noticed that ~30% of user questions in their first month of beta were compound, and that their pipeline was returning incomplete answers on most of them. Adding compound decomposition (the four patterns above) at the parsing layer raised user-reported satisfaction by a wide margin without changing anything else in the pipeline. Compound questions are common in production; pipelines that treat questions as single search strings fail on them silently.

## 8. Two outputs, one for retrieval and one for generation

The parsed question has to serve two downstream consumers with subtly different needs.

**Retrieval (Chapter 7) wants a clean search query.** Keywords, semantic groups, scope filters. No format constraints, no expected answer shape, no LLM instructions. Mixing these into the retrieval signal pollutes it: searching for "premium amount in EUR formatted as integer" returns passages that talk about formatting, not passages that contain the answer.

**Generation (Chapter 8) wants a generation brief.** The intent, the expected answer shape, the formatting requirements, the citation rules. No need for the keyword expansion or the regex variants — those were retrieval's concern.

The parsed question carries both, in separate fields:

```python
class ParsedQuestion(BaseModel):
    # ... the fields developed above
    # For retrieval (Chapter 7)
    retrieval_query: str  # clean keyword query, no format constraints
    retrieval_keywords: list[Keyword]
    retrieval_scope: ScopeFilters
    # For generation (Chapter 8)
    generation_brief: str  # what to extract, with expected format
    expected_answer_schema: type[BaseModel] | None = None
```

For "What is the premium amount in EUR, formatted as integer?":

```python
parsed = ParsedQuestion(
    original_question="What is the premium amount in EUR, formatted as integer?",
    intent="qa",
    expected_answer_shape="amount",
    # Retrieval-side
    retrieval_query="premium amount",
    retrieval_keywords=[Keyword(text="premium", ...), Keyword(text="amount", ...)],
    retrieval_scope=ScopeFilters(),
    # Generation-side
    generation_brief="Extract the premium amount. Return as integer in EUR.",
    expected_answer_schema=AmountInEuros,
)
```

The retrieval query is the clean version: "premium amount". The generation brief carries the format constraint: "as integer in EUR". The two halves don't interfere.

This split is a small thing that produces large quality gains. Many production systems take the user's question verbatim and pass it to both retrieval and generation. The result is retrieval that gets confused by formatting requirements, and generation that doesn't get clear instructions about what to extract. The split fixes both at the cost of one extra field in the parsed question.

## 9. When the question is too ambiguous to answer

Sometimes a question is genuinely ambiguous, and the right behavior is to ask the user to clarify rather than guess.

"Tell me about Smith." Smith is a common name; the corpus might contain dozens. "What's the limit?" The limit on what — coverage, deductible, sublimit, claims paid?

The parsed question carries this case in the `suggested_clarification` field:

```python
class ParsedQuestion(BaseModel):
    # ... other fields
    suggested_clarification: str | None = None
    ambiguity_reason: str | None = None
```

When set, the orchestrator surfaces the clarification to the user before running the pipeline:

> *"Several aspects of this question are ambiguous. Could you specify: which limit (coverage, deductible, sublimit), and which policy if you have multiple?"*

This is more user-friendly than guessing wrong, and more honest than producing a confident answer to the wrong question.

How does the parser decide that a question is ambiguous? Heuristics first (very short questions, missing entity references, vague terms like "this" or "that" without clear referent), LLM classification for the harder cases. The LLM is asked: "Is this question specific enough that a domain expert could answer it without follow-up? If not, what would they ask?"

The clarification mechanism is also useful when the question references something that doesn't exist in the document or corpus. "What does the warranty section say?" — but the document has no warranty section. The right answer is not to retrieve "the most warranty-related" content from elsewhere; it's to say the section doesn't exist and offer to look at related sections.

This is the same "wrong is worse than not found" principle that runs through Chapters 8 and 22, applied at parsing time. Catching ambiguity early is cheaper than catching it after retrieval has returned the wrong passages.

## 10. Three approaches to deciding activations

The execution plan field on the parsed question contains a set of activation flags — `use_toc_navigation`, `use_keyword_retrieval`, `decompose_compound`, and so on. Who decides what these are set to?

This is one of the central architectural choices of the book, and it's worth being explicit. Three approaches exist:

**Approach A — User explicit overrides.**

The user passes activation flags as arguments to `ask_document`:

```python
result = ask_document(
    question="What are all the obligations?",
    document=contract,
    use_embeddings=True,        # force semantic retrieval
    decompose_compound=False,   # force no decomposition
    iterate_on_feedback=False,  # one-shot run, no loops
)
```

**Pro**: total control, fully reproducible, debuggable. **Con**: the user has to understand the system to choose intelligently. In practice, no one does this for routine queries; it's an escape hatch for development and debugging.

**Approach B — Deterministic dispatcher.**

The system looks at the parsed question and the document profile, and applies code-based rules to decide activations:

```python
def decide_activations(parsed: ParsedQuestion, doc_profile: DocumentProfile) -> ExecutionPlan:
    plan = ExecutionPlan()  # defaults
    if parsed.intent == "summarization":
        plan.use_toc_navigation = True
        plan.use_keyword_retrieval = False  # exhaustive scope, not search
    if parsed.decomposition.pattern == "independent":
        plan.decompose_compound = True
    if doc_profile.format == "docx":
        plan.extract_page_numbers = False
    if parsed.expected_answer_shape == "list":
        plan.iterate_on_feedback = True  # listings often need refinement
    return plan
```

**Pro**: reproducible, debuggable, the team's accumulated wisdom lives in code. **Con**: requires writing and maintaining the rules. Each new question pattern that doesn't fit is a rule to add.

**Approach C — LLM-decides-everything (autonomous).**

The system describes the available sub-functions to an LLM and asks it to choose:

```python
def decide_activations(parsed: ParsedQuestion, doc_profile: DocumentProfile) -> ExecutionPlan:
    return llm.choose_activations(
        question=parsed,
        document=doc_profile,
        available_tools=AVAILABLE_TOOL_DESCRIPTIONS,
    )
```

**Pro**: flexible, gracefully handles unforeseen cases. **Con**: non-reproducible (the LLM may decide differently each run), expensive (every question costs an extra LLM call for routing), hard to debug (the reasoning is in the LLM's weights).

**The book's position: Approach B as default, with Approach A as escape hatch.**

This is the same argument we develop in detail in Chapter 15 about "agentic RAG". For enterprise contexts — legal, insurance, financial services — reproducibility, auditability, and bounded cost matter more than the marginal flexibility of Approach C. Approach B gives you all three. Approach A lets you override when you need to test a specific configuration.

Approach C is appropriate in a narrow set of contexts: genuinely open tool sets that change frequently, applications where reproducibility isn't a hard requirement, exploratory tools used by developers rather than end users. For most enterprise RAG, it's the wrong default. Chapter 15 develops this argument with the trade-offs explicitly laid out.

The practical implication for question parsing: the parser produces the parsed question; the dispatcher (in `decide_activations`, lives in the orchestrator from Chapter 15) translates the parsed question into the execution plan. Both are deterministic Python code. The LLM is involved at the *content* level — extracting keywords, classifying intent, detecting compound patterns — but not at the *control* level (deciding which sub-functions to activate).

## 11. Argument families for the public API

Once the dispatcher decides activations automatically, the user's `ask_document(question, document)` call is enough for most cases. But sometimes the user wants to override a specific behavior — force embeddings on, skip iteration, use a custom answer schema. The public API has to accommodate this without becoming unwieldy.

The pattern that holds up: **organize override arguments into four families**, each named after the brick it affects:

```python
def ask_document(
    question: str,
    document,
    
    # Question-parsing overrides (this chapter)
    intent: str | None = None,
    decomposition: str | None = None,
    keywords: list[str] | None = None,
    scope_filters: dict | None = None,
    expert_dictionary: dict | None = None,
    
    # Retrieval overrides (Chapter 7)
    retrieval_methods: list[str] | None = None,
    top_k: int | None = None,
    use_embeddings: bool | None = None,
    
    # Generation overrides (Chapter 8)
    answer_schema: type[BaseModel] | None = None,
    include_quotes: bool = True,
    include_caveats: bool = True,
    
    # Pipeline-behavior overrides (Chapters 13, 15)
    iterate_on_feedback: bool | None = None,
    max_iterations: int = 3,
    include_meta: bool = True,
) -> dict:
    ...
```

Four families. The user who wants to call `ask_document` with no overrides does it in two arguments:

```python
ask_document("What is the premium?", contract_pdf)
```

The user who wants to force a particular retrieval method does:

```python
ask_document("What is the premium?", contract_pdf, retrieval_methods=["bm25"])
```

The user who wants a custom output schema does:

```python
ask_document(
    "What is the premium?",
    contract_pdf,
    answer_schema=PremiumWithCurrencyAndFrequency,
)
```

The arguments are organized by which brick they affect, so the user knows where to look. None is required. All have sensible defaults driven by the dispatcher. The override pattern is uniform across the public API.

This same families pattern is what makes Chapter 15's composite pipeline tractable as the system grows. New activations get added to the relevant family; the API stays organized.

## 12. The output JSON's `_meta` block

The parsed question is internal to `ask_document`. But traces of it appear in the output, and that matters for the user.

The output JSON of `ask_document` has the answer (the result of generation), and it has a `_meta` block that records what was done:

```python
{
    "answer": "The premium is €125,000 annually.",
    "page_number": 4,
    "line_start": 12,
    "line_end": 14,
    "quote": "Annual premium: €125,000",
    "_meta": {
        "intent": "qa",
        "decomposition": "single",
        "activations": {
            "use_toc_navigation": True,
            "use_keyword_retrieval": True,
            "use_embeddings": False,
            "extract_page_numbers": True,
            "iterate_on_feedback": True,
        },
        "skipped": [],
        "parsing_notes": [],
        "iterations": 1,
        "retrieval_methods_used": ["toc", "keyword"],
        "model": "gpt-4.1",
        "prompt_versions": {
            "question_parsing": "v2.4",
            "generation": "v4.2",
        },
    },
}
```

The `_meta` block carries:

- The intent that was detected
- The decomposition pattern
- Which activations were on, which were off
- What was skipped (if anything) and why — from `parsing_notes`
- How many iterations the pipeline went through
- Which retrieval methods actually fired
- The model and prompt versions, for reproducibility (Chapter 23)

This isn't optional. It's what makes the system **auditable**. When a user disputes an answer, the `_meta` block is the explanation. When the team is debugging a regression, the `_meta` block is the trace. When compliance asks "why did the system give this answer," the `_meta` block is the answer.

The user who doesn't want to see `_meta` in their UI can hide it. But it's always generated and always logged, because the cost of producing it is trivial (a few extra fields in the output) and the benefit is the auditability that production deployments require.

We come back to the audit trail in Chapter 23 (production logging) and Chapter 24 (compliance). What this chapter contributes is the principle: **the question's structure flows through to the answer's `_meta`**, so the user can see the system's reasoning chain explicitly.

## 13. What to watch out for

A few traps when implementing question parsing in practice.

**Treating question parsing as just "extract keywords."** The keywords are one output among many. Pipelines that stop at keyword extraction miss intent classification, decomposition, scope filters, activation decisions — all of which affect downstream quality. The parsed question is structured; if the parsing layer produces only a keyword list, the rest of the pipeline operates on a string.

**Caching the parsed question across documents.** The parsed question depends on the document profile (Section 6). The same question parsed for a PDF and for a Word document will have different activation flags. Caching at the question text level only is wrong; the cache key must include the document profile.

**Hard-coding intent detection rules without LLM fallback.** Heuristic-only intent detection works for clearly-marked questions ("summarize", "translate") but fails on the gray cases. The LLM as fallback for ambiguous classification is cheap insurance. The cost is one mid-tier LLM call; the benefit is correct routing for the entire downstream pipeline.

**Skipping the expert dictionary because "embeddings will handle synonyms."** They handle dictionary synonyms. They do not handle internal acronyms, jurisdiction-specific terms, or business-coded vocabulary the embedding model has never seen. The expert dictionary is a permanent investment — every entry pays off for every future query that hits that vocabulary.

**Decomposing aggressively.** Over-decomposition produces incoherent answers. "What are the exclusions and limitations?" is unified, not independent, in most policy contexts; treating it as independent runs two retrievals that compete for the same passages and produces redundant output. The disambiguation test (replacing "and" with "; also") is the cheap check; the LLM classification is the safety net.

**Mixing format constraints into the retrieval query.** "Premium amount, formatted as integer, in EUR" should produce a retrieval query of "premium amount" and a generation brief that carries the format constraint. Mixing the format into retrieval pollutes the search. Always split: retrieval query for retrieval, generation brief for generation.

**Setting all activation flags by hand at every call.** This defeats the purpose of the dispatcher. The default `ask_document(q, doc)` should produce sensible activations from the parsed question and document profile. Explicit overrides are for the cases where the team genuinely knows better than the default.

**Forgetting that the parsed question is data.** The parsed question is the artifact the rest of the pipeline reads. It's worth making it inspectable, loggable, version-controlled. Production systems should be able to show "for question X, the parsed structure was Y, and that's why the system did Z."

## 14. In practice: parsing questions for the broker corpus

Some concrete examples from the insurance broker context that runs through Parts IV and V. These illustrate how parsing handles realistic enterprise questions.

**Example 1 — A point lookup with expert keywords.**

User question: *"Quel est le montant de la prime annuelle ?"*

Parsed output:

```python
ParsedQuestion(
    original_question="Quel est le montant de la prime annuelle ?",
    intent="qa",
    keywords=[
        Keyword(text="prime", weight=1.0, source="direct"),
        Keyword(text="montant", weight=0.8, source="direct"),
        Keyword(text="annuelle", weight=0.7, source="direct"),
        Keyword(text="premium", weight=0.9, source="expert_dictionary", semantic_group="prime"),
        Keyword(text="cotisation", weight=0.9, source="expert_dictionary", semantic_group="prime"),
        Keyword(text=r"\d+[\s.,]?\d*\s*(?:EUR|€)", weight=0.8,
                source="expert_dictionary", is_regex=True),
    ],
    expected_answer_shape="amount",
    decomposition=Decomposition(pattern="single"),
    scope_filters=ScopeFilters(),
    activations=ExecutionPlan(
        use_toc_navigation=True,
        use_keyword_retrieval=True,
        use_embeddings=False,
        extract_page_numbers=True,
        iterate_on_feedback=True,
    ),
    parsing_notes=["Question in French; expert dictionary applied."],
    suggested_clarification=None,
)
```

The expert dictionary expanded "prime" into French and English variants and added a regex for monetary amounts. Retrieval will use all of them. The intent is QA, the answer shape is amount, the activation flags are at sensible defaults for a point lookup.

**Example 2 — A compound question, independent decomposition.**

User question: *"What is the annual premium and what are the main exclusions?"*

Parsed output (abridged):

```python
ParsedQuestion(
    original_question="What is the annual premium and what are the main exclusions?",
    intent="qa",
    decomposition=Decomposition(
        pattern="independent",
        sub_questions=[
            "What is the annual premium?",
            "What are the main exclusions?",
        ],
    ),
    activations=ExecutionPlan(
        decompose_compound=True,
        # Other defaults
    ),
    parsing_notes=["Compound question detected. Decomposed into 2 independent sub-questions."],
)
```

The orchestrator sees `decompose_compound=True` and runs `ask_document` twice in parallel — once per sub-question — then assembles a combined output. The two halves don't compete for retrieval attention; each gets a full pipeline run.

**Example 3 — An ambiguous question that triggers clarification.**

User question: *"What's the limit?"*

Parsed output:

```python
ParsedQuestion(
    original_question="What's the limit?",
    intent="qa",
    keywords=[Keyword(text="limit", weight=1.0, source="direct")],
    expected_answer_shape="text",
    suggested_clarification=(
        "Several types of limits exist in this contract: coverage limit, sublimit, "
        "deductible, aggregate limit. Which one are you asking about?"
    ),
    ambiguity_reason="single_term_with_multiple_referents",
    activations=ExecutionPlan(),  # not running yet
    parsing_notes=["Ambiguous question; clarification suggested before running pipeline."],
)
```

The orchestrator sees `suggested_clarification` is set and surfaces it to the user instead of running the pipeline. The user picks "coverage limit," which becomes the new question, gets re-parsed cleanly, and the pipeline runs on the disambiguated input.

**Example 4 — A document-aware activation downgrade.**

User question: *"What does it say on page 3 of the contract?"*, but the contract is provided as a Word file.

Parsed output:

```python
ParsedQuestion(
    original_question="What does it say on page 3 of the contract?",
    intent="qa",
    activations=ExecutionPlan(
        extract_page_numbers=False,  # Word format — pages are renderer-dependent
        # Other defaults
    ),
    parsing_notes=[
        "User mentioned 'page 3' but document is Word format. "
        "Page numbers in Word depend on renderer; treating as approximate location.",
    ],
)
```

The orchestrator runs the pipeline without strict page-number extraction. The answer's `_meta` carries the parsing note, so the user sees the clarification: "I located content near where 'page 3' would render, but the document is Word format, so this is approximate."

**Operational metrics from production deployment.**

Six months in, here's what question parsing looks like in the broker system:

- Average parsing latency: 280 ms (one mid-tier LLM call for intent + decomposition + keyword expansion)
- Distribution by intent: QA 87%, summarization 9%, translation 4%
- Distribution by decomposition pattern: single 71%, independent 19%, conditional 6%, sequential 3%, unified 1%
- Clarification triggered on 4% of questions (mostly single-term ambiguous queries)
- Expert dictionary entries: 340, growing by 5-10 per month based on observed retrieval failures
- Document-aware activation downgrades: 12% of questions hit at least one (mostly page-number downgrades for Word files)

The parsing layer's contribution to overall accuracy was measured by ablation: with parsing disabled (treating questions as flat strings), accuracy on the per-failure-mode evaluation (Chapter 22) dropped from 91% to 76%. The 15-point gap is what question parsing buys.

## Summary

Question parsing is the symmetric counterpart of document parsing. Both bricks transform unstructured input — a document, a question — into typed, structured form that the rest of the pipeline can consume. Both are silent failure modes when done badly, and both deserve investment proportional to the complexity of what they handle.

The output of question parsing is a Pydantic object that carries the intent (QA, summarization, translation), the keywords (direct, LLM-expanded, expert-provided), the scope filters, the decomposition pattern, and the execution plan that tells the rest of the system which sub-functions to activate. A `parsing_notes` field captures things the parser noticed but couldn't enforce, which flow through to the answer's `_meta` block for auditability.

Three intents route to three different downstream pipelines. Keywords come from three sources, with the expert dictionary the most underused and often the most valuable. Scope filters narrow retrieval at the document level (Parts I-III) and become SQL clauses at the corpus level (Part IV). Compound questions decompose into four patterns — independent, sequential, unified, conditional — each with a different orchestration. Activation flags are document-aware: the same question may activate different sub-functions on a PDF and on a Word file.

The parsed question drives `ask_document(question, document)`, the public API of the system for Parts I-III. Override arguments are organized into four families — question-parsing, retrieval, generation, pipeline-behavior — so the API stays tractable as activations multiply. The default call works for most cases; expert users override what they need to.

The choice of who decides the activations matters. The book's position is that a deterministic dispatcher (Approach B) belongs in production, with user explicit overrides (Approach A) as the escape hatch for debugging. Autonomous LLM-based routing (Approach C) is rejected for enterprise contexts on grounds of reproducibility, cost, and auditability. We develop this argument in full in Chapter 15.

The next chapter takes the parsed question and the parsed document, and addresses the third brick: retrieval as scope selection. Where the structuring pair (Chapters 5 and 6) prepares the inputs, retrieval starts the production pair — selecting from the document the passages that the question's structured signals point toward. Embeddings have a role, but as a fallback rather than the default.