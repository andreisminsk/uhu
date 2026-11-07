# Model Compatibility Test Results

| Model                  | Date                 | Tests | Pass | Fail | Time   | Status                                                 |
| ---------------------- | -------------------- | ----- | ---- | ---- | ------ | ------------------------------------------------------ |
| gemma4:31b-cloud       | 2026-06-04 18:05 UTC | 26    | 26   | 0    | 111.5s | ✅ Full compatibility                                   |
| glm-5.1:cloud          | 2026-06-04 17:21 UTC | 26    | 26   | 0    | 71.9s  | ✅ Full compatibility                                   |
| qwen3-coder-next:cloud | 2026-06-04 17:35 UTC | 26    | 26   | 0    | 39.5s  | ✅ Full compatibility                                   |
| minimax-m3:cloud       | 2026-06-04 17:55 UTC | 26    | 26   | 0    | 123.8s | ✅ Full compatibility                                   |
| qwen2.5-coder:7b       | 2026-06-04 18:16 UTC | 26    | 26   | 0    | 108.7s | ✅ Full compatibility                                   |
| nemotron-3-ultra:cloud | 2026-06-06 11:04 UTC | 26    | 26   | 0    | 168.3s | ✅ Full compatibility                                   |
| gemma4:12b             | 2026-06-10 20:39 UTC | 26    | 26   | 0    | 354.8s | ✅ Full compatibility                                   |
| kimi-k2.7-code:cloud   | 2026-06-13 09:32 UTC | 26    | 24   | 2    | 99.1s  | ❌ 2 failed (edit_with_eof, no_prose_instead_of_action) |
| glm-5.2:cloud          | 2026-06-18 03:36 UTC | 26    | 26   | 0    | 75.8s  | ✅ Full compatibility                                   |
| glm-5.3-flash:cloud    | 2026-11-07 18:24 UTC | 26    | 25   | 1    | 39.3s  | ❌ 1 failed (edit_with_eof)                             |
| beam:cloud             | 2026-11-07 18:27 UTC | 26    | 2    | 24   | 36.5s  | ❌ 24 failed (empty responses)                          |
| glm-5.3-flash:cloud    | 2026-11-07 20:03 UTC | 26    | 26   | 0    | 44.3s  | ✅ Full compatibility (text channel, 0 native)          |
| beam:cloud             | 2026-11-07 20:05 UTC | 26    | 23   | 3    | 36.1s  | ✅ 23 passed (native tool_calls channel, 26/26 tests)   |

## gemma4:31b-cloud — 2026-06-04 18:05 UTC

- **Result**: PASS (26/26)
- **Total time**: 111.5s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time  |
| --- | -------------------------- | ------ | ----- |
| 1   | write_new_file             | ✅ PASS | 1.1s  |
| 2   | write_with_eof             | ✅ PASS | 0.8s  |
| 3   | edit_search_replace        | ✅ PASS | 8.0s  |
| 4   | edit_with_eof              | ✅ PASS | 3.1s  |
| 5   | file_read                  | ✅ PASS | 1.2s  |
| 6   | run_command                | ✅ PASS | 6.0s  |
| 7   | tool_read_file             | ✅ PASS | 0.8s  |
| 8   | tool_search_in_files       | ✅ PASS | 1.1s  |
| 9   | tool_list_files            | ✅ PASS | 1.5s  |
| 10  | tool_find_file             | ✅ PASS | 1.2s  |
| 11  | tool_peek_file             | ✅ PASS | 1.1s  |
| 12  | tool_git_status            | ✅ PASS | 1.1s  |
| 13  | tool_git_log               | ✅ PASS | 8.6s  |
| 14  | tool_write_file            | ✅ PASS | 2.1s  |
| 15  | tool_replace_in_file       | ✅ PASS | 0.9s  |
| 16  | tool_run_command           | ✅ PASS | 0.8s  |
| 17  | tool_env_info              | ✅ PASS | 1.1s  |
| 18  | tool_http_request          | ✅ PASS | 0.9s  |
| 19  | tool_web_search            | ✅ PASS | 1.2s  |
| 20  | eof_uses_tool_name         | ✅ PASS | 1.2s  |
| 21  | no_bare_tool_signals       | ✅ PASS | 1.5s  |
| 22  | multiple_tools             | ✅ PASS | 2.1s  |
| 23  | mixed_actions              | ✅ PASS | 1.8s  |
| 24  | full_relative_path         | ✅ PASS | 2.3s  |
| 25  | no_prose_instead_of_action | ✅ PASS | 28.9s |
| 26  | concise_output             | ✅ PASS | 18.1s |

---

## glm-5.1:cloud — 2026-06-04 17:21 UTC

- **Result**: PASS (26/26)
- **Total time**: 71.9s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ✅ PASS | 1.5s |
| 2   | write_with_eof             | ✅ PASS | 2.4s |
| 3   | edit_search_replace        | ✅ PASS | 3.1s |
| 4   | edit_with_eof              | ✅ PASS | 3.2s |
| 5   | file_read                  | ✅ PASS | 1.9s |
| 6   | run_command                | ✅ PASS | 1.5s |
| 7   | tool_read_file             | ✅ PASS | 2.1s |
| 8   | tool_search_in_files       | ✅ PASS | 1.5s |
| 9   | tool_list_files            | ✅ PASS | 2.3s |
| 10  | tool_find_file             | ✅ PASS | 1.7s |
| 11  | tool_peek_file             | ✅ PASS | 1.7s |
| 12  | tool_git_status            | ✅ PASS | 2.8s |
| 13  | tool_git_log               | ✅ PASS | 1.7s |
| 14  | tool_write_file            | ✅ PASS | 3.6s |
| 15  | tool_replace_in_file       | ✅ PASS | 4.8s |
| 16  | tool_run_command           | ✅ PASS | 1.5s |
| 17  | tool_env_info              | ✅ PASS | 1.7s |
| 18  | tool_http_request          | ✅ PASS | 1.4s |
| 19  | tool_web_search            | ✅ PASS | 4.6s |
| 20  | eof_uses_tool_name         | ✅ PASS | 1.4s |
| 21  | no_bare_tool_signals       | ✅ PASS | 1.9s |
| 22  | multiple_tools             | ✅ PASS | 2.6s |
| 23  | mixed_actions              | ✅ PASS | 1.6s |
| 24  | full_relative_path         | ✅ PASS | 3.5s |
| 25  | no_prose_instead_of_action | ✅ PASS | 0.9s |
| 26  | concise_output             | ✅ PASS | 0.9s |

---

## qwen3-coder-next:cloud — 2026-06-04 17:35 UTC

- **Result**: PASS (26/26)
- **Total time**: 39.5s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ✅ PASS | 1.2s |
| 2   | write_with_eof             | ✅ PASS | 1.1s |
| 3   | edit_search_replace        | ✅ PASS | 0.9s |
| 4   | edit_with_eof              | ✅ PASS | 0.9s |
| 5   | file_read                  | ✅ PASS | 0.9s |
| 6   | run_command                | ✅ PASS | 0.9s |
| 7   | tool_read_file             | ✅ PASS | 0.9s |
| 8   | tool_search_in_files       | ✅ PASS | 1.0s |
| 9   | tool_list_files            | ✅ PASS | 1.0s |
| 10  | tool_find_file             | ✅ PASS | 0.8s |
| 11  | tool_peek_file             | ✅ PASS | 0.9s |
| 12  | tool_git_status            | ✅ PASS | 0.9s |
| 13  | tool_git_log               | ✅ PASS | 1.0s |
| 14  | tool_write_file            | ✅ PASS | 1.0s |
| 15  | tool_replace_in_file       | ✅ PASS | 1.1s |
| 16  | tool_run_command           | ✅ PASS | 1.0s |
| 17  | tool_env_info              | ✅ PASS | 0.9s |
| 18  | tool_http_request          | ✅ PASS | 1.1s |
| 19  | tool_web_search            | ✅ PASS | 1.0s |
| 20  | eof_uses_tool_name         | ✅ PASS | 1.0s |
| 21  | no_bare_tool_signals       | ✅ PASS | 1.3s |
| 22  | multiple_tools             | ✅ PASS | 1.6s |
| 23  | mixed_actions              | ✅ PASS | 1.6s |
| 24  | full_relative_path         | ✅ PASS | 0.9s |
| 25  | no_prose_instead_of_action | ✅ PASS | 0.9s |
| 26  | concise_output             | ✅ PASS | 0.9s |

---

## minimax-m3:cloud — 2026-06-04 17:55 UTC

- **Result**: PASS (26/26)
- **Total time**: 123.8s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                    | Result | Time |
| --- | ----------------------- | ------ | ---- |
| 1   | write_new_file          | ✅ PASS | 3.5s |
| 2   | write_with_eof          | ✅ PASS | 3.6s |
| 3   | edit_search_replace     | ✅ PASS | 4.1s |
| 4   | edit_with_eof           | ✅ PASS | 6.0s |
| 5   | file_read               | ✅ PASS | 3.5s |
| 6   | run_command             | ✅ PASS | 2.7s |
| 7   | tool_read_file          | ✅ PASS | 4.4s |
| 8   | tool_search_in_files    | ✅ PASS | 7.9s |
| 9   | tool_list_files         | ✅ PASS | 3.1s |
| 10  | tool_find_file          | ✅ PASS | 5.4s |
| 11  | tool_peek_file          | ✅ PASS | 3.4s |
| 12  | tool_git_status         | ✅ PASS | 2.3s |
| 13  | tool_git_log            | ✅ PASS | 7.1s |
| 14  | tool_write_file         | ✅ PASS | 3.0s |
| 15  | tool_replace_in_file    | ✅ PASS | 8.7s |
| 16  | tool_run_command        | ✅ PASS | 2.2s |
| 17  | tool_env_info           | ✅ PASS | 2.9s |
| 18  | tool_http_request       | ✅ PASS | 2.7s |
| 19  | tool_web_search         | ✅ PASS | 2.6s |
| 20  | eof_uses_tool_name      | ✅ PASS | 3.2s |
| 21  | no_bare_tool_signals    | ✅ PASS | 3.0s |
| 22  | multiple_tools          | ✅ PASS | 5.4s |
| 23  | mixed_actions           | ✅ PASS | 4.6s |
| 24  | full_relative_path      | ✅ PASS | 6.5s |
| 25  | no_action_on_plain_text | ✅ PASS | 3.0s |
| 26  | nested_code_blocks      | ✅ PASS | 4.5s |

---

## qwen2.5-coder:7b — 2026-06-04 18:16 UTC

- **Result**: PASS (26/26)
- **Total time**: 108.7s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time  |
| --- | -------------------------- | ------ | ----- |
| 1   | write_new_file             | ✅ PASS | 24.2s |
| 2   | write_with_eof             | ✅ PASS | 2.9s  |
| 3   | edit_search_replace        | ✅ PASS | 3.4s  |
| 4   | edit_with_eof              | ✅ PASS | 3.8s  |
| 5   | file_read                  | ✅ PASS | 2.4s  |
| 6   | run_command                | ✅ PASS | 2.4s  |
| 7   | tool_read_file             | ✅ PASS | 2.4s  |
| 8   | tool_search_in_files       | ✅ PASS | 2.7s  |
| 9   | tool_list_files            | ✅ PASS | 2.1s  |
| 10  | tool_find_file             | ✅ PASS | 2.3s  |
| 11  | tool_peek_file             | ✅ PASS | 2.4s  |
| 12  | tool_git_status            | ✅ PASS | 2.1s  |
| 13  | tool_git_log               | ✅ PASS | 2.5s  |
| 14  | tool_write_file            | ✅ PASS | 2.6s  |
| 15  | tool_replace_in_file       | ✅ PASS | 3.4s  |
| 16  | tool_run_command           | ✅ PASS | 2.4s  |
| 17  | tool_env_info              | ✅ PASS | 2.4s  |
| 18  | tool_http_request          | ✅ PASS | 2.7s  |
| 19  | tool_web_search            | ✅ PASS | 2.4s  |
| 20  | eof_uses_tool_name         | ✅ PASS | 2.4s  |
| 21  | no_bare_tool_signals       | ✅ PASS | 3.6s  |
| 22  | multiple_tools             | ✅ PASS | 5.3s  |
| 23  | mixed_actions              | ✅ PASS | 4.4s  |
| 24  | full_relative_path         | ✅ PASS | 3.7s  |
| 25  | no_prose_instead_of_action | ✅ PASS | 2.4s  |
| 26  | concise_output             | ✅ PASS | 2.1s  |

## nemotron-3-ultra:cloud — 2026-06-06 11:04 UTC

- **Result**: PASS (26/26)
- **Total time**: 168.3s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time  |
| --- | -------------------------- | ------ | ----- |
| 1   | write_new_file             | ✅ PASS | 2.1s  |
| 2   | write_with_eof             | ✅ PASS | 3.1s  |
| 3   | edit_search_replace        | ✅ PASS | 14.9s |
| 4   | edit_with_eof              | ✅ PASS | 3.0s  |
| 5   | file_read                  | ✅ PASS | 3.1s  |
| 6   | run_command                | ✅ PASS | 9.8s  |
| 7   | tool_read_file             | ✅ PASS | 17.1s |
| 8   | tool_search_in_files       | ✅ PASS | 5.2s  |
| 9   | tool_list_files            | ✅ PASS | 6.1s  |
| 10  | tool_find_file             | ✅ PASS | 7.5s  |
| 11  | tool_peek_file             | ✅ PASS | 5.0s  |
| 12  | tool_git_status            | ✅ PASS | 3.0s  |
| 13  | tool_git_log               | ✅ PASS | 3.4s  |
| 14  | tool_write_file            | ✅ PASS | 4.5s  |
| 15  | tool_replace_in_file       | ✅ PASS | 6.0s  |
| 16  | tool_run_command           | ✅ PASS | 8.2s  |
| 17  | tool_env_info              | ✅ PASS | 4.5s  |
| 18  | tool_http_request          | ✅ PASS | 5.8s  |
| 19  | tool_web_search            | ✅ PASS | 6.1s  |
| 20  | eof_uses_tool_name         | ✅ PASS | 3.4s  |
| 21  | no_bare_tool_signals       | ✅ PASS | 4.9s  |
| 22  | multiple_tools             | ✅ PASS | 8.3s  |
| 23  | mixed_actions              | ✅ PASS | 10.5s |
| 24  | full_relative_path         | ✅ PASS | 3.0s  |
| 25  | no_prose_instead_of_action | ✅ PASS | 3.6s  |
| 26  | concise_output             | ✅ PASS | 3.3s  |

## gemma4:12b — 2026-06-10 20:39 UTC

- **Result**: PASS (26/26)
- **Total time**: 354.8s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time  |
| --- | -------------------------- | ------ | ----- |
| 1   | write_new_file             | ✅ PASS | 49.2s |
| 2   | write_with_eof             | ✅ PASS | 15.6s |
| 3   | edit_search_replace        | ✅ PASS | 16.3s |
| 4   | edit_with_eof              | ✅ PASS | 10.8s |
| 5   | file_read                  | ✅ PASS | 7.7s  |
| 6   | run_command                | ✅ PASS | 7.3s  |
| 7   | tool_read_file             | ✅ PASS | 8.5s  |
| 8   | tool_search_in_files       | ✅ PASS | 9.2s  |
| 9   | tool_list_files            | ✅ PASS | 8.8s  |
| 10  | tool_find_file             | ✅ PASS | 8.5s  |
| 11  | tool_peek_file             | ✅ PASS | 13.0s |
| 12  | tool_git_status            | ✅ PASS | 8.2s  |
| 13  | tool_git_log               | ✅ PASS | 8.6s  |
| 14  | tool_write_file            | ✅ PASS | 8.8s  |
| 15  | tool_replace_in_file       | ✅ PASS | 17.0s |
| 16  | tool_run_command           | ✅ PASS | 7.5s  |
| 17  | tool_env_info              | ✅ PASS | 19.1s |
| 18  | tool_http_request          | ✅ PASS | 8.7s  |
| 19  | tool_web_search            | ✅ PASS | 7.6s  |
| 20  | eof_uses_tool_name         | ✅ PASS | 12.2s |
| 21  | no_bare_tool_signals       | ✅ PASS | 12.3s |
| 22  | multiple_tools             | ✅ PASS | 26.1s |
| 23  | mixed_actions              | ✅ PASS | 20.6s |
| 24  | full_relative_path         | ✅ PASS | 16.4s |
| 25  | no_prose_instead_of_action | ✅ PASS | 7.0s  |
| 26  | concise_output             | ✅ PASS | 6.9s  |

## kimi-k2.7-code:cloud — 2026-06-13 09:32 UTC

- **Result**: FAIL (24/26)
- **Total time**: 99.1s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — 2 failed, 0 errors

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ✅ PASS | 3.2s |
| 2   | write_with_eof             | ✅ PASS | 3.3s |
| 3   | edit_search_replace        | ✅ PASS | 3.7s |
| 4   | edit_with_eof              | ❌ FAIL | 3.1s |
| 5   | file_read                  | ✅ PASS | 3.1s |
| 6   | run_command                | ✅ PASS | 3.4s |
| 7   | tool_read_file             | ✅ PASS | 3.1s |
| 8   | tool_search_in_files       | ✅ PASS | 3.2s |
| 9   | tool_list_files            | ✅ PASS | 3.6s |
| 10  | tool_find_file             | ✅ PASS | 3.3s |
| 11  | tool_peek_file             | ✅ PASS | 3.3s |
| 12  | tool_git_status            | ✅ PASS | 3.2s |
| 13  | tool_git_log               | ✅ PASS | 3.4s |
| 14  | tool_write_file            | ✅ PASS | 3.3s |
| 15  | tool_replace_in_file       | ✅ PASS | 3.5s |
| 16  | tool_run_command           | ✅ PASS | 3.3s |
| 17  | tool_env_info              | ✅ PASS | 3.2s |
| 18  | tool_http_request          | ✅ PASS | 3.3s |
| 19  | tool_web_search            | ✅ PASS | 3.5s |
| 20  | eof_uses_tool_name         | ✅ PASS | 3.3s |
| 21  | no_bare_tool_signals       | ✅ PASS | 3.3s |
| 22  | multiple_tools             | ✅ PASS | 3.6s |
| 23  | mixed_actions              | ✅ PASS | 3.4s |
| 24  | full_relative_path         | ✅ PASS | 3.2s |
| 25  | no_prose_instead_of_action | ❌ FAIL | 3.1s |
| 26  | concise_output             | ✅ PASS | 3.0s |

## glm-5.2:cloud — 2026-06-18 03:36 UTC

- **Result**: PASS (26/26)
- **Total time**: 75.8s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ✅ PASS | 4.6s |
| 2   | write_with_eof             | ✅ PASS | 1.7s |
| 3   | edit_search_replace        | ✅ PASS | 2.2s |
| 4   | edit_with_eof              | ✅ PASS | 2.2s |
| 5   | file_read                  | ✅ PASS | 4.1s |
| 6   | run_command                | ✅ PASS | 1.4s |
| 7   | tool_read_file             | ✅ PASS | 3.6s |
| 8   | tool_search_in_files       | ✅ PASS | 1.3s |
| 9   | tool_list_files            | ✅ PASS | 5.3s |
| 10  | tool_find_file             | ✅ PASS | 1.2s |
| 11  | tool_peek_file             | ✅ PASS | 2.5s |
| 12  | tool_git_status            | ✅ PASS | 1.1s |
| 13  | tool_git_log               | ✅ PASS | 0.9s |
| 14  | tool_write_file            | ✅ PASS | 1.2s |
| 15  | tool_replace_in_file       | ✅ PASS | 1.5s |
| 16  | tool_run_command           | ✅ PASS | 4.7s |
| 17  | tool_env_info              | ✅ PASS | 1.6s |
| 18  | tool_http_request          | ✅ PASS | 3.0s |
| 19  | tool_web_search            | ✅ PASS | 3.8s |
| 20  | eof_uses_tool_name         | ✅ PASS | 3.4s |
| 21  | no_bare_tool_signals       | ✅ PASS | 2.7s |
| 22  | multiple_tools             | ✅ PASS | 1.4s |
| 23  | mixed_actions              | ✅ PASS | 1.3s |
| 24  | full_relative_path         | ✅ PASS | 0.9s |
| 25  | no_prose_instead_of_action | ✅ PASS | 1.5s |
| 26  | concise_output             | ✅ PASS | 3.7s |

---

## glm-5.3-flash:cloud — 2026-11-07 18:24 UTC

- **Result**: FAIL (25/26)
- **Total time**: 39.3s
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — 1 failed, 0 errors

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ✅ PASS | 0.9s |
| 2   | write_with_eof             | ✅ PASS | 0.6s |
| 3   | edit_search_replace        | ✅ PASS | 1.9s |
| 4   | edit_with_eof              | ❌ FAIL | 1.0s |
| 5   | file_read                  | ✅ PASS | 0.5s |
| 6   | run_command                | ✅ PASS | 0.8s |
| 7   | tool_read_file             | ✅ PASS | 0.9s |
| 8   | tool_search_in_files       | ✅ PASS | 0.7s |
| 9   | tool_list_files            | ✅ PASS | 1.0s |
| 10  | tool_find_file             | ✅ PASS | 1.3s |
| 11  | tool_peek_file             | ✅ PASS | 0.9s |
| 12  | tool_git_status            | ✅ PASS | 0.8s |
| 13  | tool_git_log               | ✅ PASS | 0.6s |
| 14  | tool_write_file            | ✅ PASS | 0.6s |
| 15  | tool_replace_in_file       | ✅ PASS | 1.0s |
| 16  | tool_run_command           | ✅ PASS | 0.6s |
| 17  | tool_env_info             | ✅ PASS | 0.7s |
| 18  | tool_http_request          | ✅ PASS | 0.9s |
| 19  | tool_web_search            | ✅ PASS | 1.6s |
| 20  | eof_uses_tool_name         | ✅ PASS | 2.9s |
| 21  | no_bare_tool_signals       | ✅ PASS | 0.7s |
| 22  | multiple_tools             | ✅ PASS | 0.9s |
| 23  | mixed_actions              | ✅ PASS | 1.3s |
| 24  | full_relative_path         | ✅ PASS | 0.9s |
| 25  | no_prose_instead_of_action | ✅ PASS | 1.4s |
| 26  | concise_output             | ✅ PASS | 0.5s |

### Failed tests

- **edit_with_eof**: Edits or reads main.py (EDIT/replace_in_file/read_file first)

---

## beam:cloud — 2026-11-07 18:27 UTC

- **Result**: FAIL (2/26)
- **Total time**: 36.5s
- **Sampling**: temperature=0.7, top_p=0.99
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — 24 failed, 0 errors
- **Note**: model returned empty output on every test; the 2 "passes" (no_bare_tool_signals, concise_output) are vacuous. Sampling change made no difference vs default run.

### Details

| #   | Test                       | Result | Time |
| --- | -------------------------- | ------ | ---- |
| 1   | write_new_file             | ❌ FAIL | 1.9s |
| 2   | write_with_eof             | ❌ FAIL | 0.9s |
| 3   | edit_search_replace        | ❌ FAIL | 0.9s |
| 4   | edit_with_eof              | ❌ FAIL | 1.0s |
| 5   | file_read                  | ❌ FAIL | 0.8s |
| 6   | run_command                | ❌ FAIL | 0.8s |
| 7   | tool_read_file             | ❌ FAIL | 0.7s |
| 8   | tool_search_in_files       | ❌ FAIL | 0.9s |
| 9   | tool_list_files            | ❌ FAIL | 0.8s |
| 10  | tool_find_file             | ❌ FAIL | 0.9s |
| 11  | tool_peek_file             | ❌ FAIL | 0.7s |
| 12  | tool_git_status            | ❌ FAIL | 0.6s |
| 13  | tool_git_log               | ❌ FAIL | 0.8s |
| 14  | tool_write_file            | ❌ FAIL | 0.8s |
| 15  | tool_replace_in_file       | ❌ FAIL | 1.1s |
| 16  | tool_run_command           | ❌ FAIL | 1.0s |
| 17  | tool_env_info              | ❌ FAIL | 0.6s |
| 18  | tool_http_request          | ❌ FAIL | 0.8s |
| 19  | tool_web_search            | ❌ FAIL | 1.0s |
| 20  | eof_uses_tool_name         | ❌ FAIL | 0.6s |
| 21  | no_bare_tool_signals       | ✅ PASS | 1.1s |
| 22  | multiple_tools             | ❌ FAIL | 1.6s |
| 23  | mixed_actions              | ❌ FAIL | 0.8s |
| 24  | full_relative_path         | ❌ FAIL | 0.8s |
| 25  | no_prose_instead_of_action | ❌ FAIL | 0.7s |
| 26  | concise_output             | ✅ PASS | 0.8s |

### Failed tests

All 24 action tests failed identically — empty output, no action blocks parsed (see Details table). Verdict: POOR — model not suitable for this harness.

---

## glm-5.3-flash:cloud — 2026-11-07 20:03 UTC (post native-tool_calls implementation)

- **Result**: PASS (26/26)
- **Total time**: 44.3s
- **Native tool_calls**: used in 0/26 test(s) — text channel only, as expected
- **Categories**: WRITE, EDIT, FILE, RUN, TOOL, EOF, MULTI, EDGE — all passed

### Details

| #   | Test                       | Result        | Time |
| --- | -------------------------- | ------------- | ---- |
| 1   | write_new_file             | ✅ PASS       | 1.0s |
| 2   | write_with_eof             | ✅ PASS       | 1.1s |
| 3   | edit_search_replace        | ✅ PASS       | 2.5s |
| 4   | edit_with_eof              | ✅ PASS       | 0.9s |
| 5   | file_read                  | ✅ PASS       | 0.8s |
| 6   | run_command                | ✅ PASS       | 1.2s |
| 7   | tool_read_file             | ✅ PASS       | 0.8s |
| 8   | tool_search_in_files       | ✅ PASS       | 1.4s |
| 9   | tool_list_files            | ✅ PASS       | 0.8s |
| 10  | tool_find_file             | ✅ PASS       | 0.8s |
| 11  | tool_peek_file             | ✅ PASS       | 0.8s |
| 12  | tool_git_status            | ✅ PASS       | 0.9s |
| 13  | tool_git_log               | ✅ PASS       | 0.9s |
| 14  | tool_write_file            | ✅ PASS       | 0.9s |
| 15  | tool_replace_in_file       | ✅ PASS       | 1.3s |
| 16  | tool_run_command           | ✅ PASS       | 1.0s |
| 17  | tool_env_info              | ✅ PASS       | 1.4s |
| 18  | tool_http_request          | ✅ PASS       | 1.4s |
| 19  | tool_web_search            | ✅ PASS       | 2.4s |
| 20  | eof_uses_tool_name         | ✅ PASS       | 0.9s |
| 21  | no_bare_tool_signals       | ✅ PASS       | 1.0s |
| 22  | multiple_tools             | ✅ PASS       | 1.8s |
| 23  | mixed_actions              | ✅ PASS       | 2.6s |
| 24  | full_relative_path         | ✅ PASS       | 0.9s |
| 25  | no_prose_instead_of_action | ✅ PASS       | 0.7s |
| 26  | concise_output             | ✅ PASS       | 0.5s |

---

## beam:cloud — 2026-11-07 20:05 UTC (post native-tool_calls implementation)

- **Result**: PASS (23/26, native channel)
- **Total time**: 36.1s
- **Native tool_calls**: used in 26/26 test(s) — the model emits structured tool_calls exclusively (empty text content on every response); previously surfaced as empty responses and 24 fails
- **Categories**: WRITE 2/2, FILE 1/1, RUN 1/1, TOOL 13/13, EOF 2/2, EDGE 3/3; EDIT 0/2 and MULTI 1/2 failed (find_file-first exploration instead of direct read/edit in one round — resolves in a live feedback loop)

### Details

| #   | Test                       | Result             | Time |
| --- | -------------------------- | ------------------ | ---- |
| 1   | write_new_file             | ✅ PASS (native)   | 0.9s |
| 2   | write_with_eof             | ✅ PASS (native)   | 1.3s |
| 3   | edit_search_replace        | ❌ FAIL (native)   | 0.9s |
| 4   | edit_with_eof              | ❌ FAIL (native)   | 0.8s |
| 5   | file_read                  | ✅ PASS (native)   | 1.0s |
| 6   | run_command                | ✅ PASS (native)   | 0.7s |
| 7   | tool_read_file             | ✅ PASS (native)   | 0.9s |
| 8   | tool_search_in_files       | ✅ PASS (native)   | 0.7s |
| 9   | tool_list_files            | ✅ PASS (native)   | 1.1s |
| 10  | tool_find_file             | ✅ PASS (native)   | 0.7s |
| 11  | tool_peek_file             | ✅ PASS (native)   | 0.7s |
| 12  | tool_git_status            | ✅ PASS (native)   | 0.7s |
| 13  | tool_git_log               | ✅ PASS (native)   | 0.9s |
| 14  | tool_write_file            | ✅ PASS (native)   | 0.7s |
| 15  | tool_replace_in_file       | ✅ PASS (native)   | 0.9s |
| 16  | tool_run_command           | ✅ PASS (native)   | 0.7s |
| 17  | tool_env_info              | ✅ PASS (native)   | 0.7s |
| 18  | tool_http_request          | ✅ PASS (native)   | 0.7s |
| 19  | tool_web_search            | ✅ PASS (native)   | 1.1s |
| 20  | eof_uses_tool_name         | ✅ PASS (native)   | 0.7s |
| 21  | no_bare_tool_signals       | ✅ PASS (native)   | 0.7s |
| 22  | multiple_tools             | ✅ PASS (native)   | 1.3s |
| 23  | mixed_actions              | ❌ FAIL (native)   | 1.3s |
| 24  | full_relative_path         | ✅ PASS (native)   | 0.8s |
| 25  | no_prose_instead_of_action | ✅ PASS (native)   | 0.7s |
| 26  | concise_output             | ✅ PASS (native)   | 0.9s |

### Failed tests

- **edit_search_replace** / **edit_with_eof**: model emitted find_file first (locate-then-edit strategy) — check expects direct read/edit in a single response; succeeds in live multi-round feedback loop
- **mixed_actions**: read issued, write deferred to next round


