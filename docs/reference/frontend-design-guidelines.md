# Web UI Design Guidelines

## Reference

Primary reference: `/Users/helap/Downloads/BjtTestBench.jsx`.

Secondary static reference: `/Users/helap/Downloads/bjt-test-bench-apple.html`.

The production GUI should follow the React component prototype directly. Do not reinterpret the app as IBM Carbon, Linear, or a generic dashboard unless the reference changes.

## Design Direction

Use a macOS / iOS HIG inspired desktop instrument interface:

- Three-column layout: left control sidebar, central measurement workspace, right AI inspector.
- Component structure maps to: TitleBar, Sidebar, MainContent, AIPanel, StatusBar.
- Light window background with translucent-feeling side rails.
- SF / PingFang style typography.
- Rounded cards, soft shadows, hairline separators.
- System blue for primary actions.
- System red only for emergency stop and dangerous hardware operations.
- AI panel behaves like an inspector/chat rail, not a marketing chatbot.

## Tokens

- Window: `#ececee`
- Content: `#f5f5f7`
- Sidebar rail: `rgba(246,246,248,0.72)`
- Card: `#ffffff`
- Inset: `#f2f2f7`
- Fill: `rgba(120,120,128,0.12)`
- Fill strong: `rgba(120,120,128,0.20)`
- Label: `#1d1d1f`
- Secondary label: `#6e6e73`
- Tertiary label: `#9a9aa0`
- Blue: `#007aff`
- Red: `#ff3b30`
- Green: `#34c759`
- Separator: `rgba(0,0,0,0.08)`

## Layout Rules

- Left sidebar width should be close to 268px.
- Right AI inspector width should be close to 320px.
- Main workspace should hold the plot, live metrics, test point table, and log.
- Cards use 12px radius and subtle shadow.
- Controls use 8px radius.
- Avoid dense square enterprise styling.
- Avoid oversized marketing spacing.
- Keep the app usable at approximately 1320x860.

## AI Panel Rules

- Header: `BJT-AI`, clear button, and a compact “测试对话” selector.
- Transcript area should be long and quiet.
- Composer card sits near the bottom.
- Composer order: mode/provider, model, API key, natural language input, send.
- No shortcut chips unless explicitly requested.
