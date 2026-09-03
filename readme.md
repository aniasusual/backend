uvicorn engine:app --host 127.0.0.1 --port 8000 --reload


sequenceDiagram
    autonumber
    actor User
    participant WelcomeView as WelcomeView.jsx
    participant App as App.jsx
    participant EngineAPI as engine.py (FastAPI REST)
    participant TemplateMgr as template_manager.py
    participant EngineWS as engine.py (WebSocket /ws)
    participant ToolReg as tools/registry.py
    participant ProcTools as tools/process_tools.py
    participant Harness as coding_harness.py
    participant AgentLoader as agent_loader.py
    participant ContextMgr as context_manager.py
    participant Ollama as Ollama Local LLM
    participant StreamDisp as stream_normalizer.py
    participant Subagents as subagents (Design/UI)
    participant FileTools as tools/file_tools.py
    participant PreviewPanel as PreviewPanel.jsx

    User->>WelcomeView: Enters prompt & hits Enter
    WelcomeView->>EngineAPI: GET /api/projects/suggest-name?base=...
    EngineAPI-->>WelcomeView: Returns suggested project name
    WelcomeView->>App: onSubmit(prompt, projectName)
    App->>EngineAPI: POST /api/projects {name, template: "node_react"}
    EngineAPI->>TemplateMgr: scaffold_project(project_path)
    TemplateMgr-->>EngineAPI: Files copied + cached node_modules symlinked
    EngineAPI-->>App: ProjectInfo {name, path, status}
    
    App->>EngineWS: WS send: {"action": "open_project", "name": projectName}
    EngineWS->>ToolReg: ToolRegistry(sandbox_path, sync_send_event)
    EngineWS->>ProcTools: active_registry.start_dev_server()
    ProcTools-->>EngineWS: Vite on port 3000, Express on port 5001
    EngineWS-->>App: WS event: {"type": "preview_ready", "port": 3000, "url": "..."}
    App->>PreviewPanel: Set previewData & start health polling
    
    App->>EngineWS: WS send: {"prompt": prompt, "harness": "CodingHarness", "model": model}
    EngineWS->>Harness: run_harness_task(prompt, "CodingHarness", model)
    Harness->>AgentLoader: AgentLoader.get_profile_for_model(model)
    AgentLoader-->>Harness: AgentProfile (whitelisted tools, subagents, system prompt)
    Harness->>ContextMgr: ContextManager.prepare_messages(prompt, system_prompt, history)
    
    loop Agentic Execution Loop (up to max_iterations)
        Harness->>Ollama: client.chat(model, messages, tools=active_schemas, stream=True)
        Ollama-->>Harness: Chunks (thinking / content / tool_calls)
        Harness->>StreamDisp: Dispatch tokens & suppress raw JSON
        StreamDisp-->>EngineWS: {"type": "thinking"} or {"type": "token"}
        EngineWS-->>App: Stream token into ChatMessage.jsx
        
        alt Tool Call: invoke_design_agent
            Harness->>Subagents: DesignSubagent.generate_layout_blueprint()
            Subagents->>FileTools: Inject HSL tokens & Google Fonts into src/index.css
        else Tool Call: write_files / write_file
            Harness->>FileTools: write_file("server/index.js", expressCode)
            Harness->>FileTools: write_file("src/App.jsx", reactCode)
            FileTools-->>EngineWS: {"type": "file_changed"}
            EngineWS-->>App: Event: file_changed
            App->>PreviewPanel: Debounced auto-reload iframe
        else Tool Call: lint_javascript
            Harness->>ToolReg: LinterTools.lint_javascript("src/App.jsx")
        else Tool Call: finish
            Harness->>ToolReg: InteractionTools.finish(summary)
        end
        Harness->>ContextMgr: Append tool result to messages
    end
    Harness-->>EngineWS: {"type": "status", "content": "Done"}
    EngineWS-->>App: Agent completes, collapses tool cards
