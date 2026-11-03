# UHU-CACHE-ANALYSIS-OPENAI

## OpenAI API cache analysis --- long agentic coding session

### Session configuration

The custom agent was run with:

``` text
--model gpt-5.5
--ctx 1050000
--max-context 100000
--tpm 100000
```

Interpretation:

-   `gpt-5.5` --- model used by the coding agent.
-   `--ctx 1050000` --- agent is configured for a \~1.05M-token model
    context capability.
-   `--max-context 100000` --- the agent actually limits the working
    context to \~100K tokens.
-   `--tpm 100000` --- the agent limits throughput to 100K
    tokens/minute.

The 100K working-context limit is substantially below the model's
nominal 1.05M context capacity, which can make context behavior and cost
more predictable.

------------------------------------------------------------------------

## Observed API statistics

After one long coding session:

  Metric                               Value
  ----------------------------- ------------
  Cache hit rate                   **95.9%**
  Cache-read tokens                 **4.3M**
  Cache-write tokens (30 min)          **0**
  Cache-write tokens (12 hr)           **0**
  Uncached tokens                 **183.4K**

### Token accounting

Approximate total input-token volume:

``` text
4.3M cached
+ 183.4K uncached
----------------
≈ 4.483M total input tokens
```

The reported hit rate is consistent with:

``` text
4.3M / (4.3M + 183.4K) ≈ 95.9%
```

Thus approximately **96% of the input-token volume was served from
cache**.

Only about **4.1%** was uncached.

------------------------------------------------------------------------

## What this means for an agentic coding workflow

This is a very strong cache-utilization result.

A long-running coding agent typically makes many API calls while
retaining a large, relatively stable prompt prefix. That prefix can
contain:

-   system instructions
-   agent operating rules
-   tool definitions
-   project/repository context
-   conversation history
-   persistent task state

The high cache-hit rate indicates that a large majority of the repeated
context remained cacheable across requests.

In practical terms, the agent was able to process roughly **4.48M input
tokens of total traffic** while only **183.4K tokens required uncached
processing**.

This is exactly the usage pattern in which prompt caching becomes
particularly valuable.

------------------------------------------------------------------------

## Approximate input-cost effect

Using the GPT-5.5 prices assumed in the original analysis:

``` text
Standard input:        $5 / 1M tokens
Cached input:        $0.50 / 1M tokens
```

Approximate cached-input cost:

``` text
4.3M × $0.50/M ≈ $2.15
```

Approximate uncached-input cost:

``` text
183.4K × $5/M ≈ $0.92
```

Approximate total input cost:

``` text
$2.15 + $0.92 ≈ $3.07
```

If the same \~4.483M tokens had all been uncached:

``` text
4.483M × $5/M ≈ $22.42
```

Approximate input-cost difference:

``` text
$22.42 - $3.07 ≈ $19.35
```

So, under those pricing assumptions, caching reduced the
input-processing cost by roughly **86%**, saving approximately **\$19**
over this session's input volume.

**Important:** this calculation covers input tokens only. Output-token
charges, if any, are separate.

------------------------------------------------------------------------

## Architectural observation

The combination of:

``` text
max-context = 100K
```

and:

``` text
95.9% cache hit
```

suggests that the custom agent is maintaining a highly stable reusable
prompt prefix while changing only a relatively small portion of each
request.

That is desirable for an agentic coding architecture.

A simplified pattern might look like:

``` text
Request 1   ~80K context
Request 2   ~82K context
Request 3   ~85K context
...
Request N   ~97K context
```

If most of the beginning of those requests remains identical, the API
can reuse the cached portion instead of processing all those tokens as
new input every time.

The observed statistics strongly support that interpretation, although
the cache statistics alone do not reveal exactly which portions of the
prompt were cached.

------------------------------------------------------------------------

## Important distinction: context vs. cache

These are different concepts:

### Context capacity

The model may support a very large maximum context:

``` text
~1.05M tokens
```

### Agent working-context limit

The custom agent is configured to use:

``` text
100K tokens
```

### Cache volume

The session accumulated:

``` text
4.3M cache-read tokens
```

This does **not** mean that 4.3M tokens were simultaneously present in
one context window.

It means that across many API requests, the API served a cumulative
\~4.3M tokens from the prompt cache.

This distinction is important when interpreting the statistics.

------------------------------------------------------------------------

## Overall assessment

**95.9% cache hit rate is an excellent result for a long-running agentic
coding session.**

The session demonstrates:

1.  **High prompt reuse** --- about 96% of input tokens were cached.
2.  **Low uncached fraction** --- only \~183K tokens were processed as
    uncached input.
3.  **Large cumulative workload** --- roughly 4.48M input tokens passed
    through the API.
4.  **Effective stable-prefix architecture** --- the agent appears to
    preserve a large reusable context across iterative calls.
5.  **Significant potential cost reduction** --- under the pricing
    assumptions above, input cost was roughly 86% lower than it would
    have been without caching.

The result is particularly favorable for a coding agent because agentic
workflows tend to make many sequential calls against the same project
and accumulated context.

------------------------------------------------------------------------

## Caveats

-   Cache statistics are cumulative across API requests; they do not
    represent one 4.3M-token prompt.
-   The exact monetary result depends on the model, API pricing
    applicable to the account, and the exact token categories reported
    by the API.
-   Output-token costs are not included in the calculations above.
-   A high cache-hit rate does not by itself prove that the agent's
    context-management strategy is optimal; it shows that the repeated
    input is highly cacheable.
-   Pricing and model limits can change. Verify current OpenAI
    documentation before using these figures for budgeting.

## Bottom line

``` text
Model:             gpt-5.5
Agent context:     100K
Total input:       ~4.48M tokens
Cached:            4.3M tokens
Uncached:          183.4K tokens
Cache hit rate:    95.9%

Assessment:        Excellent cache utilization
```
