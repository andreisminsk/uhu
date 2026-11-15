# Changelog

All notable changes per release. Versions tracked in `uhu-ver.txt`; commits landing between version bumps accumulate under the following bump.

## [2.2.2] - 2026-11-15

- Fix think-level value parsing.

## [2.2.1] - 2026-11-12

- Fix TypeError in jobs.
- Docker: install libatomic1 — Playwright driver node needs it before --with-deps can run.
- --max-tokens arg for OpenAI API implemented.

## [2.1.5] - 2026-11-10

- Fix TypeError in jobs.

## [2.1.4] - 2026-11-09

- Fix [AGENT] prefix.

## [2.1.3] - 2026-11-09

- Fix mixing text blocks into tool_call blocks.

## [2.1.2] - 2026-11-08

- Fix deprecated CLI option.

## [2.1.1] - 2026-11-08

- Native tools calling fixes.
- Native tools calling fixes.
- Native tools calling fixes.
- Cross-send loop radar + wrap-up grace gating (beam:cloud field fixes).
- Native tools calling fixes.
- Mcp fix.

## [2.1.0] - 2026-11-08

- Major refactor: migratinf to native tools.

## [2.0.1] - 2026-11-08

- Test the model with parameters temperature and top_p.
- Implement native tool_calls handling, beam and mistral4 llm support.

## [1.26.1] - 2026-11-07

- Nidge command implemented.

## [1.25.3] - 2026-11-03

- Fix sleep output and link to job.

## [1.25.2] - 2026-11-03

- Fix terminal hanging after CPR.

## [1.25.1] - 2026-11-03

- Sleep tool extended with job and process id.

## [1.24.2] - 2026-11-03

- README update.
- README updated.
- Fix truncation in (d) confirmation option input.

## [1.24.1] - 2026-11-03

- Fix spinner interrupt.
- Fix duplicate observations.
- Add self-awareness via README.md hint.
- File Cache/Rollback fixes.

## [1.23.1] - 2026-11-02

- --think-level CLI argument and inline command implemented.

## [1.22.1] - 2026-11-02

- Max-rounds support, audio alert, one-shot long prompt file.

## [1.21.1] - 2026-11-01

- README.md updated with info about Python certs failing.
- External skills documnted.
- Fix skill load truncation.
- Add temperature and sound.

## [1.20.2] - 2026-10-23

- Fix prompt_toolkit race condiion crash.

## [1.20.1] - 2026-10-22

- Guardrail for sys.exit(1) in generated script.

## [1.19.2] - 2026-10-20

- Add /llm command logging.

## [1.19.1] - 2026-10-19

- Added info about reasoning efforts settings into README.md.
- Token stats added.

## [1.18.1] - 2026-10-16

- Fix MCP support.

## [1.17.3] - 2026-10-15

- Ui_automation - key modifiers.

## [1.17.2] - 2026-10-15

- Fix /compact memory.

## [1.17.1] - 2026-10-15

- Fix coordinates in ui_automation tool.

## [1.16.1] - 2026-10-12

- Docker updated -  resilience mimics music-gen.
- /compact force command implemented.

## [1.15.2] - 2026-10-11

- Docker updated with README served at SANDBOX.

## [1.15.1] - 2026-10-11

- Uhu home, secrets and skills config refactored.

## [1.14.2] - 2026-10-11

- Llama and huggingface examples added.

## [1.14.1] - 2026-10-09

- Replace_in_file tool tuned.

## [1.13.1] - 2026-10-09

- Tools implemented py_test and npm_build.

## [1.12.1] - 2026-10-09

- README update.
- Cache stats implemented.

## [1.11.1] - 2026-10-05

- OpenAI cache stats added.
- Logo and app-icon added.
- Logo and app-icon added.
- Ughu logo.

## [1.11.0] - 2026-09-28

- Privacy modes implemented.

## [1.10.0] - 2026-09-28

- Implement ui-automation tool.

## [1.9.0] - 2026-09-27

- --openai-extra-body parameter implemented to enable openrouter provider selection.
- Web_fetch system prompt tuning.

## [1.8.0] - 2026-09-27

- README-ANDROID.md added.
- --openai-extra-body parameter implemented to enable openrouter provider selection.

## [1.7.2] - 2026-09-24

- Openai install optional.

## [1.7.1] - 2026-09-24

- Playwright install optional.

## [1.7.0] - 2026-09-24

- Fix Docker build.
- Thinking output to support narrow terminal, openai and playwrite to install.

## [1.6.0] - 2026-09-22

- Fix browser tool, fix py_compile context pollution.

## [1.5.1] - 2026-09-21

- Sys_info fix - GPU load stats.

## [1.5.0] - 2026-09-21

- Fix app naming.
- Sys-info tool updated with multi-core runpod case.

## [1.4.1] - 2026-09-21

- Updates check improved.

## [1.4.0] - 2026-09-21

- Updates check improved.

## [1.3.1] - 2026-09-21

- Changed default models from deprecated to glm-5.3-flash:cloud.
- AI output coloring.
- Color scheme set explicit for AI.
- Color scheme set explicit for AI.
- Updates check improved.

## [1.3.0] - 2026-09-21

- Custom .skills web-search to overcome IP blacklisting.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Docker image build added.
- Changed default models from deprecated to glm-5.3-flash:cloud.

## [1.2.1] - 2026-09-05

- Merge branch 'main' of https://github.com/andreisminsk/uhu.
- /workdir inline command implemented.

## [1.1.1] - 2026-09-05

- Fix name in .toml.
- Add disk space measurements.

## [1.0.2] - 2026-09-04

- Feedback info added.
- Fix top ram measurements.

## [1.0.1] - 2026-09-02

- Packaging as python app implemented.

## [0.83.1] - 2026-09-02

- Missing dependency added.
- Llm_chat tool implemented.

## [0.82.1] - 2026-09-02

- System info tools implemented.

## [0.81.1] - 2026-08-30

- /llm command implemented.

## [0.80.1] - 2026-08-25

- Sleep tool implemented.

## [0.77.2] - 2026-08-25

- Fix async check for updates.

## [0.77.1] - 2026-08-25

- Fix action signature ignoring param values.

## [0.76.1] - 2026-08-24

- Implemented check for updates.

## [0.75.1] - 2026-08-24

- Ollama timeout guide added.
- Merge branch 'main' of https://github.com/andreisminsk/uhu.
- Fix job output leak into main console.

## [0.74.1] - 2026-08-22

- Implemented /timeout command.

## [0.73.1] - 2026-08-18

- Fix jobs.
- Fix /compact failing after /restore.

## [0.72.1] - 2026-08-13

- Fix jobs.

## [0.71.1] - 2026-08-12

- Nudge logic refinement.

## [0.70.1] - 2026-08-12

- Implement LLM parsing as fallback.

## [0.68.2] - 2026-08-11

- Fix parser risky constants handling.

## [0.68.1] - 2026-08-11

- Fix parser backticks without language.

## [0.67.2] - 2026-08-09

- Added support for timeout parameter to image-analysis tool.

## [0.67.1] - 2026-08-09

- Add ollama stats.
- Added support for model parameter to image-analysis tool.

## [0.66.1] - 2026-08-01

- Image paste via Alt+V implemented.

## [0.65.1] - 2026-07-31

- Readme updated.
- Figma MCP added.
- Browser tool fixes.

## [0.64.1] - 2026-07-29

- Fix image analysis settings pick up.

## [0.63.1] - 2026-07-29

- OpenAI support added.
- OpenAI support added.
- OpenAI API support added - with TPL limits.
- OpenAI API support added - with TPL limits.

## [0.61.1] - 2026-07-29

- OpenAi support added.

## [0.60.3] - 2026-07-29

- Fix browser calls.

## [0.60.2] - 2026-07-26

- Fix runtime error after browser tool.

## [0.60.1] - 2026-07-25

- Fix browser tool invocation.

## [0.59.1] - 2026-07-25

- Added running jobs indicator.

## [0.58.1] - 2026-07-24

- /pid command + parent PID.

## [0.57.3] - 2026-07-23

- Fix failure on unicode symbols.

## [0.57.2] - 2026-07-18

- Fix corrupt job json.

## [0.57.1] - 2026-07-17

- Add zsh MacOS shell command handling.

## [0.56.1] - 2026-07-16

- Input fixes.

## [0.55.1] - 2026-07-16

- MacOS terminal fixes.

## [0.41.1] - 2026-07-11

- Graph-ai skill: mindmap style support.

## [0.40.1] - 2026-07-11

- Refactoring major.

## [0.37.1] - 2026-07-11

- Learn-pythion skill added.
- Learn-pythion skill added.
- Sessions naming and restore refined.

## [0.36.2] - 2026-07-10

- Parser vulnerability fixes.

## [0.36.1] - 2026-07-10

- Parser fixes - powershell support.

## [0.35.2] - 2026-07-10

- Parser fixes.

## [0.35.1] - 2026-07-10

- Enforced markup rule.
- Lazy loading of skills implemented.

## [0.34.2] - 2026-07-10

- Typing practice custom skill added.
- Enforced markup rule.

## [0.34.1] - 2026-07-08

- Jobs system implemented.

## [0.32.1] - 2026-07-07

- Persona names introduced.

## [0.31.3] - 2026-07-07

- Fix py_compile, git-uncommitted.

## [0.31.2] - 2026-07-07

- File_link tool fix.

## [0.31.1] - 2026-07-07

- Git-uncommitted skill added.

## [0.30.1] - 2026-07-06

- Fix duplicate confirmations.

## [0.29.2] - 2026-07-05

- Make py_compile safe tool.

## [0.29.1] - 2026-07-05

- Auto-safe tools list updated.

## [0.28.1] - 2026-07-04

- Mermaid mcp added.
- New skill implemented: svg2png.

## [0.27.1] - 2026-07-04

- Mermaid mcp added.

## [0.26.1] - 2026-07-04

- Added new skill: graph-ai.

## [0.25.1] - 2026-07-04

- Added support for MCP server enabled flag.

## [0.24.2] - 2026-07-02

- Date-awareness added.

## [0.24.1] - 2026-06-30

- Added disclaimer in pro-bidder.

## [0.23.1] - 2026-06-29

- Custom skill added: video-timestamp.
- Custom skill added: video-timestamp.

## [0.22.1] - 2026-06-28

- Fix image-analysis output truncated.

## [0.21.1] - 2026-06-28

- Web_search refactored.

## [0.20.1] - 2026-06-27

- Added calculator tool.

## [0.19.1] - 2026-06-27

- /embed-bin command added to allow image processing by main model.

## [0.18.1] - 2026-06-27

- Revise copyright and author details in LICENSE.
- GitHub mcp configured.
- Text-writer skill added.

## [0.17.1] - 2026-06-27

- Added docx2md skill.

## [0.16.1] - 2026-06-27

- Improved invocation of built-in skills.
- Added token-count tool.

## [0.15.1] - 2026-06-26

- Set of built-in skills extended with what-if, root-cause, problem-solving, architect, medicine, business-coach.
- Set of built-in skills extended with pro-bidder.

## [0.14.1] - 2026-06-26

- Weather and geo-loc tools implemented.

## [0.13.2] - 2026-06-25

- Agent color applied to /restore output.

## [0.13.1] - 2026-06-24

- MCP mode implemented.
- Copyright notice to README.md.
- Added color distinction for agent and tool output.

## [0.12.1] - 2026-06-22

- MCP mode implemented.
- MCP mode implemented.

## [0.11.2] - 2026-06-21

- README.md updated with new step in Ollama installation.
- README.md updated with new step in Ollama installation.
- Fix parse_actions error.

## [0.11.1] - 2026-06-21

- One-shot mode implemented.

## [0.10.1] - 2026-06-18

- Giving model a hint to produce max 3 files at once.
- Malformed Json instruction check.
- Model test added Ollama glm-5.2:cloud.
- Md2pdf moved to permanent skills.

## [0.9.1] - 2026-06-14

- README.md updated.
- Readme updated.
- Readme updated.
- Readme and LICENSE updated.
- Fixed parser skipping files exceeding threshold.

## [0.9.0] - 2026-06-13

- First commit.
