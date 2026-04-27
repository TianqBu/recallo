# vhs tape — render with `vhs docs/demo.tape` (https://github.com/charmbracelet/vhs)
# Output: docs/demo.gif. Run from a clean machine with OPENAI_API_KEY set.

Output docs/demo.gif

Set FontSize 14
Set Width 1000
Set Height 600
Set Theme "Dracula"
Set TypingSpeed 60ms

Type "# Recallo — local-first browser agent with long-term memory"
Sleep 600ms
Enter
Type "pip install git+https://github.com/TianqBu/recallo.git"
Sleep 800ms
Enter
Sleep 4s

Type "recallo init"
Sleep 400ms
Enter
Sleep 1500ms

Type 'recallo explore "Summarize the Self-RAG paper from arxiv 2310.11511"'
Sleep 400ms
Enter
Sleep 12s

Type "# ---- close the terminal, come back tomorrow ----"
Sleep 1500ms
Enter

Type 'recallo recall "what did that paper say about retrieval?"'
Sleep 400ms
Enter
Sleep 3s

Type "recallo replay"
Sleep 400ms
Enter
Sleep 3s
