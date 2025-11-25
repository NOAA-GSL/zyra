## Executive Summary

This document synthesizes an analysis of the Model Context Protocol (MCP), an open standard developed by Anthropic to connect AI agents with external tools and systems. While promoted as a universal solution to integration fragmentation, the standard implementation of MCP through direct tool calls suffers from severe inefficiencies, particularly at scale. These issues have prompted a significant strategic shift toward a "code execution" model, which itself is subject to conflicting interpretations.

The primary challenges with the direct tool-calling approach are twofold:

1.  **Tool Definition Overload:** Agents must load the definitions of all available tools into the context window upfront, consuming vast numbers of tokens and increasing costs and latency before a user request is even processed.
2.  **Intermediate Result Bloat:** Each tool call and its result must pass back through the model, carrying the entire preceding conversation history. This method exponentially increases token consumption for multi-step tasks, degrades model performance, and risks exceeding context window limits.

In response, Anthropic has detailed a "[code execution](https://www.anthropic.com/engineering/code-execution-with-mcp)" approach, also referred to as "Code Mode" by Cloudflare. In this model, agents write code (e.g., TypeScript) to interact with tools presented as code APIs. This method allows agents to load only the specific tools they need on-demand and to process, filter, and transform data within a separate execution environment before passing concise results to the model. Anthropic reports this can reduce token usage by as much as 98.7%.

However, this pivot is viewed critically by [some observers](https://youtu.be/1piFEKA9XL0?list=TLGG-rNIRus4Hl0xNjExMjAyNQ). One prominent critique frames this development not as an evolution, but as a public admission by Anthropic that the MCP standard is fundamentally flawed, inefficient, and impractical for real-world applications. This perspective argues that the code execution model is a necessary workaround that effectively bypasses the core issues of the protocol, which is seen as an example of an "AI bubble" where more effort is spent on building tooling for a flawed concept than on creating useful products.

## The Model Context Protocol (MCP): Purpose and Flaws

### Stated Purpose and Adoption

The Model Context Protocol (MCP) is an open standard designed to create a universal protocol for connecting AI agents to external tools and data. Its stated goal is to eliminate the need for custom integrations for each agent-tool pairing, thereby reducing fragmentation and duplicated development effort. According to Anthropic, since its launch in November 2024, MCP has seen rapid adoption, with thousands of community-built servers, SDKs for all major programming languages, and its establishment as the "de-facto standard."

### Core Inefficiencies and Criticisms

Despite its stated goals, the standard implementation of MCP via direct tool calls has been identified as being deeply inefficient and flawed, leading to significant performance and cost issues.

#### A. Tool Definition Overload

The most common MCP pattern requires clients to load all available tool definitions directly into the model's context window. This creates an immediate and substantial token burden.

*   **Problem:** For agents connected to hundreds or thousands of tools, this can mean processing "hundreds of thousands of tokens before reading a request," according to Anthropic.
*   **Critique:** This design is seen as fundamentally misguided. One critic notes, "Models do not get smarter when you give them more tools. They get smarter when you give them a small subset of really good tools. An MCP does not encourage that way of thinking."
*   **Real-World Example:** The agent for the tool Trey was observed to have 23 tools constantly available in its context. This included seven file management tools and three tools for Superbase, even for users who have never used the Superbase service, illustrating how irrelevant context is consistently loaded for every request.

#### B. Intermediate Results and Context Bloat

In a direct tool-calling workflow, every intermediate step must be processed by the model, compounding the token overload.

*   **Mechanism:** When an agent performs a multi-step task (e.g., get a document, then update a record), the full result of the first tool call is loaded into the context. The model then uses this expanded context to make the second call. As one analyst describes it, "every additional tool call is carrying all of the previous context... It's so much bloat."
*   **Quantified Impact:** Anthropic provides an example where processing a 2-hour sales meeting transcript could require an additional 50,000 tokens because the full text must pass through the model twice.
*   **Consequences:** This process dramatically increases costs, slows down response times, and makes the models "dumber and worse" by overwhelming them with context. In some cases, large documents can exceed the context window entirely, breaking the workflow.

#### C. Fundamental Protocol Flaws

Beyond inefficiency, critics point to fundamental omissions in the MCP specification itself.

*   **Lack of Authentication:** A significant criticism is that "MCP has no concept of O auth at all." This lack of a standardized authentication mechanism makes secure handshakes difficult, forcing developers to rely on insecure workarounds like hardcoding signed parameters into URLs.
*   **Overly Simplistic Design:** The protocol is described as a "Python spec" that, in its attempt to be "simple and elegant," forgot to include the necessary "meat." This has led developers from other ecosystems (e.g., TypeScript) to find the standard frustrating and incomplete.

#### D. Market Perception

The protocol has been described as a "favorite example of AI being a bubble." The argument is that the ecosystem around MCP is inverted: "I know way more companies building observability tools for MCP stuff than I know companies actually making useful stuff with MCP." This is compared to the Web3 bubble, where infrastructure and tooling companies proliferated without a corresponding number of useful applications. The perception is that MCP adoption is driven by "people trying to sell you things, not people trying to make useful things."

## The Code Execution Solution

In response to the scaling challenges of direct tool calls, Anthropic and others in the community (notably Cloudflare with its "Code Mode") have championed a new approach where agents write and execute code to interact with MCP servers.

### Core Concept

Instead of exposing tools directly to the model, MCP servers are presented as code APIs. The AI agent's task becomes writing code—typically in a language like TypeScript—to call these APIs. This fundamentally changes the workflow: agents can load only the tools they need for a specific task and process data within a secure execution environment before passing only the final, relevant results back to the model.

This shift is seen by critics as a vindication of their initial skepticism, with one stating, "Thank you Enthropic for admitting I was right the whole fucking time."

### Quantified Impact

The efficiency gains from this approach are substantial. In an example of retrieving a document from Google Drive and updating a Salesforce record, Anthropic reports the following improvement:

*   **Direct Tool Calls:** 150,000 tokens
*   **Code Execution:** 2,000 tokens
*   **Result:** A time and cost saving of **98.7%**.

This stark figure has been highlighted by critics as definitive proof of the original protocol's inadequacy: "The creators of MCP are sitting here and telling us that writing shit TypeScript code is 99% more effective than using their spec as they wrote it."

### Key Benefits of Code Execution

| **Benefit** | **Description** |
|--------------|-----------------|
| **Progressive Disclosure** | Models can discover tools on-demand by navigating a file system (e.g., `/servers/salesforce/updateRecord.ts`) or by using a `search_tools` function, rather than having all definitions loaded upfront. |
| **Context-Efficient Results** | Agents can perform complex data operations (filtering, aggregation, joins) in code. For a 10,000-row spreadsheet, the model might only see a 5-row summary instead of the entire dataset, preventing context bloat. |
| **Powerful Control Flow** | Complex logic like loops and conditionals can be handled with standard programming constructs. This is faster and more reliable, as code is deterministic, whereas an LLM might hallucinate when evaluating logic within a massive context. |
| **Enhanced Privacy** | Intermediate results and sensitive data remain within the execution environment and do not enter the model's context by default. The agent only needs to know what to do with the data, not see the data itself. PII can also be automatically tokenized before any information is logged or returned to the model. |
| **State Persistence & "Skills"** | Agents can maintain state across operations by writing intermediate results to files. They can also save their own generated code as reusable functions or "skills," creating a library of higher-level capabilities over time. |

## Analysis and Conflicting Perspectives

The move toward code execution reveals a deep tension in the AI agent development space.

#### A. Official Narrative vs. Critical Interpretation

*   **Anthropic's Position:** Code execution is presented as a sophisticated pattern for scaling agent capabilities, applying established software engineering solutions (like SDKs) to the novel problems of AI agents. It is framed as an evolution of MCP for more complex use cases.
*   **Critical View:** This narrative is rejected as revisionism. The critical perspective is that Anthropic's blog post is a tacit admission that the original MCP spec is broken. The 98.7% efficiency gain is not seen as an improvement but as evidence of a foundational failure.

#### B. The "Skills" Reinvention Loop

The concept of agents saving their generated code as reusable "skills" with `SKILL.md` documentation files has been met with cynicism. One critic argues this is simply reinventing MCP on a new layer of abstraction:

1.  Start with a direct API call.
2.  Standardize it into an MCP tool definition.
3.  Realize it's inefficient and convert it into an SDK-like code interface.
4.  Save this useful code as a "skill" with documentation.
5.  End up "roughly where we started."

This cycle is mockingly referred to as "the real agentic loop."

#### C. Contradictory Views on Security

Anthropic's article notes that code execution introduces "operational overhead and security considerations that direct tool calls avoid." This is a point of major contention.

*   A critic vehemently refutes this, calling the statement "absolute fucking bullshit" and "delusion."
*   The counter-argument is that direct tool calls via MCP are inherently insecure due to the protocol's lack of a standardized authentication concept. Therefore, a properly sandboxed code execution environment is significantly more secure than the baseline offered by MCP.

#### D. Conclusion: The Developer Divide

The debate over MCP and code execution highlights a broader theme: "Devs should be defining what devs use." The perceived failures of MCP are presented as a case study of what happens when "LLM people" design APIs and protocols without a deep understanding of established software engineering principles. The ultimate success of code execution is seen as proof that classic programming constructs remain superior to flawed, AI-centric abstractions.