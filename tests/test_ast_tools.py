import os
import tempfile
from pathlib import Path

import pytest

from tools.ast_tools import ASTTools
from tools.registry import ToolRegistry
from tools.schemas import TOOL_SCHEMAS
from plugins.argument_normalizer import ToolArgumentNormalizer
from tools.parser import ToolCallParser
from context.estimator import TokenEstimator


import shutil
from config.settings import PROJECTS_ROOT

@pytest.fixture
def sandbox():
    """Provides an isolated sandbox workspace under PROJECTS_ROOT for testing."""
    test_dir = PROJECTS_ROOT / "_test_ast_tools"
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield test_dir
    finally:
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def ast_tools(sandbox):
    return ASTTools(
        sandbox_path=sandbox,
        is_safe_path_fn=lambda p: ".." not in Path(p).parts and not str(p).startswith("/"),
    )


@pytest.fixture
def registry(sandbox):
    return ToolRegistry(
        sandbox_dir=sandbox,
        model_name="qwen2.5-coder:14b",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Python AST Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_python_signatures_classes_and_functions(ast_tools, sandbox):
    python_code = '''"""Module level docstring for user service."""

import os
from typing import List, Optional, Dict, Any

GLOBAL_CONST = "SYSTEM_CONSTANT"
TYPED_VAR: int = 42

@decorator_a
@decorator_b(param="val")
async def fetch_user_data(user_id: int, timeout: Optional[float] = 5.0) -> Dict[str, Any]:
    """Fetch user data from primary store."""
    query = f"SELECT * FROM users WHERE id = {user_id}"
    res = await db.execute(query)
    for row in res:
        if row.is_valid:
            print("Found valid user record")
    return {"id": user_id, "data": res}


class UserService(BaseService):
    """Main user management business service."""
    service_name: str = "user_svc"
    MAX_RETRIES = 3

    def __init__(self, config: Dict[str, Any]):
        """Initialize user service with runtime configuration."""
        self.config = config
        self.active = True
        self.setup_connections()

    @property
    def is_active(self) -> bool:
        return self.active

    @staticmethod
    def format_name(first: str, last: str) -> str:
        """Format full legal name."""
        return f"{first.strip()} {last.strip()}".title()
'''
    py_file = sandbox / "user_service.py"
    py_file.write_text(python_code, encoding="utf-8")

    result = ast_tools.extract_signatures("user_service.py")

    # Header verification
    assert "[AST Signature Map: user_service.py" in result
    assert "token reduction" in result

    # Docstrings preserved
    assert 'Module level docstring for user service.' in result
    assert 'Fetch user data from primary store.' in result
    assert 'Main user management business service.' in result
    assert 'Initialize user service with runtime configuration.' in result
    assert 'Format full legal name.' in result

    # Function and class headers preserved with type annotations
    assert "async def fetch_user_data(user_id: int, timeout: Optional[float]=5.0) -> Dict[str, Any]:" in result
    assert "class UserService(BaseService):" in result
    assert "def __init__(self, config: Dict[str, Any]):" in result
    assert "def format_name(first: str, last: str) -> str:" in result
    assert "@property" in result
    assert "@staticmethod" in result
    assert "@decorator_a" in result
    assert "service_name: str = 'user_svc'" in result or 'service_name: str = "user_svc"' in result

    # Body implementation lines stripped
    assert 'SELECT * FROM users' not in result
    assert 'print("Found valid user record")' not in result
    assert 'self.setup_connections()' not in result
    assert 'return {"id": user_id' not in result

    # Token reduction achieved
    orig_tokens = TokenEstimator.estimate_text(python_code)
    sig_tokens = TokenEstimator.estimate_text(result)
    assert sig_tokens < orig_tokens


def test_extract_python_token_reduction_on_heavy_body(ast_tools, sandbox):
    heavy_code = [
        "import math",
        "",
        "def compute_heavy_statistics(data: list[float]) -> dict[str, float]:",
        '    """Compute statistical aggregates."""',
    ]
    # Add 150 lines of body logic
    for i in range(150):
        heavy_code.append(f"    v_{i} = math.sqrt({i}) * math.sin(data[{i % 5}])")
    heavy_code.append("    return {'mean': 0.0, 'variance': 1.0}")

    content = "\n".join(heavy_code)
    (sandbox / "stats.py").write_text(content, encoding="utf-8")

    result = ast_tools.extract_signatures("stats.py")

    assert "def compute_heavy_statistics" in result
    assert "Compute statistical aggregates" in result
    assert "v_100" not in result
    assert "v_149" not in result

    orig_tokens = TokenEstimator.estimate_text(content)
    sig_tokens = TokenEstimator.estimate_text(result)
    reduction = 100 - (sig_tokens * 100 // orig_tokens)
    assert reduction >= 80, f"Expected >= 80% reduction, got {reduction}%"


# ─────────────────────────────────────────────────────────────────────────────
# 2. JavaScript / Express Route Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_js_signatures_starter_template(ast_tools, sandbox):
    """Verifies against the exact Lowkey starter backend template (server/index.js)."""
    starter_path = Path(__file__).parent.parent / "templates" / "node_react" / "server" / "index.js"
    if not starter_path.exists():
        pytest.skip("Starter template server/index.js not found.")

    starter_content = starter_path.read_text(encoding="utf-8")
    server_target = sandbox / "server" / "index.js"
    server_target.parent.mkdir(parents=True, exist_ok=True)
    server_target.write_text(starter_content, encoding="utf-8")

    result = ast_tools.extract_signatures("server/index.js")

    # Header verification
    assert "[AST Signature Map: server/index.js" in result
    assert "lines" in result

    # Imports preserved
    assert "import express from 'express';" in result
    assert "import cors from 'cors';" in result

    # Route definitions preserved with handler signatures
    assert "app.get('/api/health'" in result
    assert "app.get('/api/items'" in result
    assert "app.post('/api/items'" in result
    assert "app.put('/api/items/:id'" in result
    assert "app.delete('/api/items/:id'" in result
    assert "app.listen(PORT" in result

    # All route bodies are stripped to { /* ... */ }
    assert "res.json({ status: 'ok'" not in result
    assert "items.unshift(newItem);" not in result
    assert "items.findIndex(i => i.id === req.params.id)" not in result
    assert "res.json({ success: true, id: req.params.id });" not in result


def test_extract_js_express_routes_heavy_service(ast_tools, sandbox):
    heavy_server = """
import express from 'express';
import cors from 'cors';

const app = express();
const PORT = process.env.BACKEND_PORT || 5001;

app.use(cors());
app.use(express.json());

// In-memory data store
let items = [
    { id: "1", title: "Item 1", desc: "First test item description for mock database store" },
    { id: "2", title: "Item 2", desc: "Second test item description for mock database store" },
    { id: "3", title: "Item 3", desc: "Third test item description for mock database store" },
    { id: "4", title: "Item 4", desc: "Fourth test item description for mock database store" }
];

app.get('/api/users', async (req, res) => {
    try {
        const query = req.query.search;
        const page = parseInt(req.query.page) || 1;
        const limit = 20;
        const offset = (page - 1) * limit;
        console.log("Processing user query with parameters:", { query, page, limit });
        const users = await db.users.findMany({
            where: query ? { name: { contains: query } } : {},
            skip: offset,
            take: limit,
            orderBy: { createdAt: "desc" }
        });
        const total = await db.users.count();
        res.json({ users, total, page, pages: Math.ceil(total / limit) });
    } catch (err) {
        console.error("Failed to fetch users:", err);
        res.status(500).json({ error: "Internal server error", details: err.message });
    }
});

app.post('/api/users', async (req, res) => {
    try {
        const { email, name, role } = req.body;
        if (!email || !name) {
            return res.status(400).json({ error: "Email and name are required fields" });
        }
        const existing = await db.users.findUnique({ where: { email } });
        if (existing) {
            return res.status(409).json({ error: "User already exists with this email address" });
        }
        const user = await db.users.create({
            data: { email, name, role: role || "user", createdAt: new Date() }
        });
        console.log("Successfully created new user account:", user.id);
        res.status(201).json(user);
    } catch (err) {
        console.error("Failed to create user account:", err);
        res.status(500).json({ error: "Internal server error", details: err.message });
    }
});

app.put('/api/users/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { name, role } = req.body;
        const existing = await db.users.findUnique({ where: { id } });
        if (!existing) {
            return res.status(404).json({ error: "User record not found for update" });
        }
        const updated = await db.users.update({
            where: { id },
            data: { name, role, updatedAt: new Date() }
        });
        console.log("Updated user account record:", id);
        res.json(updated);
    } catch (err) {
        console.error("Failed to update user account:", err);
        res.status(500).json({ error: err.message });
    }
});

app.delete('/api/users/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const existing = await db.users.findUnique({ where: { id } });
        if (!existing) {
            return res.status(404).json({ error: "User record not found for deletion" });
        }
        await db.users.delete({ where: { id } });
        console.log("Deleted user account record:", id);
        res.sendStatus(204);
    } catch (err) {
        console.error("Failed to delete user account:", err);
        res.status(500).json({ error: err.message });
    }
});

app.listen(PORT, () => {
    console.log(`Server started on port ${PORT}`);
});
"""
    (sandbox / "server.js").write_text(heavy_server, encoding="utf-8")

    result = ast_tools.extract_signatures("server.js")

    assert "app.get('/api/users'" in result
    assert "app.post('/api/users'" in result
    assert "app.put('/api/users/:id'" in result
    assert "app.delete('/api/users/:id'" in result
    assert "app.listen(PORT" in result

    # Zero body lines
    assert "const offset = (page - 1) * limit;" not in result
    assert "db.users.findUnique" not in result
    assert "db.users.delete" not in result

    orig_tokens = TokenEstimator.estimate_text(heavy_server)
    sig_tokens = TokenEstimator.estimate_text(result)
    reduction = 100 - (sig_tokens * 100 // orig_tokens)
    assert reduction >= 80, f"Expected >= 80% reduction, got {reduction}%"

def test_extract_signatures_multi_line_routes_and_whitespace(ast_tools, sandbox):
    server_code = """
import express from 'express';
const app = express();

app.get(
    '/api/v1/orders/:orderId',
    authMiddleware,
    async (req, res) => {
        const order = await db.orders.findById(req.params.orderId);
        res.json(order);
    }
);

app.listen(
    5001,
    '0.0.0.0',
    () => {
        console.log('Running on port 5001');
    }
);
"""
    (sandbox / "multiline_server.js").write_text(server_code, encoding="utf-8")

    # 1. Whitespace in file_path
    res = ast_tools.extract_signatures("   multiline_server.js   ")
    assert "app.get(" in res
    assert "/api/v1/orders/:orderId" in res
    assert "authMiddleware" in res
    assert "app.listen(" in res
    assert "const order = await db.orders.findById" not in res
    assert "console.log('Running on port 5001');" not in res


# ─────────────────────────────────────────────────────────────────────────────
# 3. React / JSX Component Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_jsx_react_component(ast_tools, sandbox):
    jsx_code = """
import React, { useState, useEffect } from 'react';
import { Trash2, PlusCircle, Check } from 'lucide-react';

export default function TodoApp({ initialFilter = 'all' }) {
    const [todos, setTodos] = useState([]);
    const [filter, setFilter] = useState(initialFilter);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            const res = await fetch('/api/items');
            const data = await res.json();
            setTodos(data);
            setLoading(false);
        };
        loadData();
    }, []);

    const handleAdd = async (text) => {
        const res = await fetch('/api/items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: text })
        });
        const created = await res.json();
        setTodos(prev => [created, ...prev]);
    };

    const handleDelete = async (id) => {
        await fetch(`/api/items/${id}`, { method: 'DELETE' });
        setTodos(prev => prev.filter(t => t.id !== id));
    };

    return (
        <div className="todo-container min-h-screen bg-slate-900 text-white p-8">
            <header className="mb-6 flex justify-between items-center">
                <h1 className="text-3xl font-bold">Todo Workspace</h1>
            </header>
            <main>
                {todos.map(t => (
                    <div key={t.id} className="todo-item flex items-center p-4 border-b border-slate-700">
                        <span>{t.title}</span>
                        <button onClick={() => handleDelete(t.id)}>Delete</button>
                    </div>
                ))}
            </main>
        </div>
    );
}

export function TodoBadge({ count, label }) {
    return (
        <span className="badge px-2 py-1 rounded bg-blue-500 text-xs">
            {label}: {count}
        </span>
    );
}
"""
    (sandbox / "TodoApp.jsx").write_text(jsx_code, encoding="utf-8")

    result = ast_tools.extract_signatures("TodoApp.jsx")

    # Components and hooks preserved
    assert "function TodoApp" in result
    assert "useState" in result
    assert "handleAdd" in result
    assert "handleDelete" in result

    # JSX layout lines collapsed
    assert '<div className="todo-container min-h-screen' not in result
    assert '<header className="mb-6' not in result
    assert 'Todo Workspace</h1>' not in result

    orig_tokens = TokenEstimator.estimate_text(jsx_code)
    sig_tokens = TokenEstimator.estimate_text(result)
    assert sig_tokens < orig_tokens


# ─────────────────────────────────────────────────────────────────────────────
# 4. TypeScript / TSX Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_typescript_interfaces_and_types(ast_tools, sandbox):
    ts_code = """
import { Request, Response } from 'express';

export interface UserProfile {
    id: string;
    username: string;
    email: string;
    role: 'admin' | 'user' | 'guest';
    createdAt: Date;
}

export type AuthState = 'unauthenticated' | 'authenticating' | 'authenticated' | 'error';

export enum ProjectStatus {
    DRAFT = 'draft',
    ACTIVE = 'active',
    ARCHIVED = 'archived'
}

export class AuthService {
    private tokenSecret: string;

    constructor(secret: string) {
        this.tokenSecret = secret;
        console.log("Initialized auth service");
    }

    public async verifyToken(token: string): Promise<UserProfile | null> {
        try {
            const decoded = jwt.verify(token, this.tokenSecret);
            return decoded as UserProfile;
        } catch {
            return null;
        }
    }
}
"""
    (sandbox / "types.ts").write_text(ts_code, encoding="utf-8")

    result = ast_tools.extract_signatures("types.ts")

    assert "interface UserProfile" in result
    assert "type AuthState" in result
    assert "enum ProjectStatus" in result
    assert "class AuthService" in result
    assert "verifyToken" in result
    assert 'console.log("Initialized auth service");' not in result


# ─────────────────────────────────────────────────────────────────────────────
# 5. Registry & Dispatch Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_extract_signatures_delegation(registry, sandbox):
    py_code = "def add(a: int, b: int) -> int:\n    '''Add two integers.'''\n    return a + b\n"
    (sandbox / "math_ops.py").write_text(py_code, encoding="utf-8")

    # Call directly via registry method
    res1 = registry.extract_signatures("math_ops.py")
    assert "def add(a: int, b: int) -> int:" in res1
    assert "Add two integers" in res1
    assert "return a + b" not in res1

    # Call via registry get_tools() dictionary mapping
    tools_map = registry.get_tools()
    assert "extract_signatures" in tools_map
    res2 = tools_map["extract_signatures"]("math_ops.py")
    assert res2 == res1


def test_registry_extract_signatures_in_tool_functions(registry):
    tool_fns = registry.get_tool_functions()
    fn_names = [fn.__name__ for fn in tool_fns]
    assert "extract_signatures" in fn_names


def test_schema_extract_signatures_present():
    names = [s.get("function", {}).get("name") for s in TOOL_SCHEMAS]
    assert "extract_signatures" in names

    schema = next(s for s in TOOL_SCHEMAS if s.get("function", {}).get("name") == "extract_signatures")
    props = schema["function"]["parameters"]["properties"]
    assert "file_path" in props
    assert "file_path" in schema["function"]["parameters"]["required"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Argument Normalization & Tool Parser Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_argument_normalizer_aliases_for_extract_signatures():
    cases = [
        ({"path": "server/index.js"}, {"file_path": "server/index.js"}),
        ({"file": "src/App.jsx"}, {"file_path": "src/App.jsx"}),
        ({"target_file": "app.py"}, {"file_path": "app.py"}),
        ({"filename": "types.ts"}, {"file_path": "types.ts"}),
        ({"filepath": "utils.js"}, {"file_path": "utils.js"}),
    ]
    for inp, expected in cases:
        normalized = ToolArgumentNormalizer.normalize("extract_signatures", inp)
        assert normalized == expected


def test_tool_call_parser_extract_signatures_tag():
    text = '<extract_signatures>{"file_path": "server/index.js"}</extract_signatures>'
    calls = ToolCallParser.extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["name"] == "extract_signatures"
    assert calls[0]["arguments"]["file_path"] == "server/index.js"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Security, Sandboxing, and Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_signatures_path_traversal_rejection(ast_tools):
    res = ast_tools.extract_signatures("../outside.py")
    assert "Error: Access denied" in res


def test_extract_signatures_nonexistent_file(ast_tools):
    res = ast_tools.extract_signatures("does_not_exist.py")
    assert "Error: Target file does not exist" in res


def test_extract_signatures_directory_error(ast_tools, sandbox):
    sub = sandbox / "src"
    sub.mkdir()
    res = ast_tools.extract_signatures("src")
    assert "Target path is a directory" in res
    assert "locate_files_by_pattern" in res


def test_extract_signatures_unsupported_extension(ast_tools, sandbox):
    (sandbox / "notes.txt").write_text("Plain text notes.")
    res = ast_tools.extract_signatures("notes.txt")
    assert "Notice: extract_signatures currently supports" in res
    assert "read_file" in res


def test_extract_signatures_empty_file(ast_tools, sandbox):
    (sandbox / "empty.py").write_text("")
    res = ast_tools.extract_signatures("empty.py")
    assert "Empty file (0 lines)" in res


# ─────────────────────────────────────────────────────────────────────────────
# 8. Repository Dependency Graph Mapping Tests (ITEM-10, CP-105.1)
# ─────────────────────────────────────────────────────────────────────────────

def test_map_dependencies_react_component_graph(ast_tools, sandbox):
    # Set up multi-file React component structure
    src = sandbox / "src"
    components = src / "components"
    utils = src / "utils"
    components.mkdir(parents=True, exist_ok=True)
    utils.mkdir(parents=True, exist_ok=True)

    (src / "main.jsx").write_text("""
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
""", encoding="utf-8")

    (src / "index.css").write_text("body { margin: 0; }", encoding="utf-8")

    (src / "App.jsx").write_text("""
import React, { useState } from 'react';
import TodoList from './components/TodoList';
import Header from './components/Header';
import { API_BASE_URL } from './config';

export default function App() {}
""", encoding="utf-8")

    (src / "config.js").write_text("""
export const API_BASE_URL = 'http://localhost:5001';
""", encoding="utf-8")

    (components / "Header.jsx").write_text("""
import React from 'react';
import { User, Bell } from 'lucide-react';

export default function Header() {}
""", encoding="utf-8")

    (components / "TodoList.jsx").write_text("""
import React, { useState } from 'react';
import TodoItem from './TodoItem';
import { formatDate } from '../utils/date';

export default function TodoList() {}
export const DEFAULT_FILTER = 'all';
""", encoding="utf-8")

    (components / "TodoItem.jsx").write_text("""
import React from 'react';
import { Trash2, CheckCircle } from 'lucide-react';

export default function TodoItem({ todo }) {}
export const ITEM_STATUSES = ['active', 'completed'];
""", encoding="utf-8")

    (utils / "date.js").write_text("""
export function formatDate(d) { return d.toISOString(); }
""", encoding="utf-8")

    # 1. Targeted impact analysis for TodoItem.jsx
    target_res = ast_tools.map_dependencies("src/components/TodoItem.jsx")
    assert "[DEPENDENCY IMPACT ANALYSIS: src/components/TodoItem.jsx]" in target_res
    assert "default (TodoItem)" in target_res
    assert "ITEM_STATUSES" in target_res
    # External packages
    assert "react" in target_res
    assert "lucide-react" in target_res
    # Downstream dependents: TodoList imports TodoItem!
    assert "src/components/TodoList.jsx" in target_res

    # 2. Targeted impact analysis for TodoList.jsx
    list_res = ast_tools.map_dependencies("src/components/TodoList.jsx")
    assert "[DEPENDENCY IMPACT ANALYSIS: src/components/TodoList.jsx]" in list_res
    # Imports local files
    assert "src/components/TodoItem.jsx" in list_res
    assert "src/utils/date.js" in list_res
    # Downstream dependents: App imports TodoList!
    assert "src/App.jsx" in list_res

    # 3. Whole-project dependency topology map
    full_res = ast_tools.map_dependencies()
    assert "[WORKSPACE DEPENDENCY TOPOLOGY MAP]" in full_res
    assert "ENTRY POINTS" in full_res
    assert "src/main.jsx" in full_res
    assert "EXTERNAL PACKAGES USED" in full_res
    assert "react" in full_res
    assert "lucide-react" in full_res
    assert "src/components/TodoList.jsx" in full_res


def test_map_dependencies_node_express_backend(ast_tools, sandbox):
    server = sandbox / "server"
    routes = server / "routes"
    routes.mkdir(parents=True, exist_ok=True)

    (server / "index.js").write_text("""
import express from 'express';
import cors from 'cors';
import itemsRouter from './routes/items';
import authRouter from './routes/auth';

const app = express();
app.use('/api/items', itemsRouter);
app.use('/api/auth', authRouter);
""", encoding="utf-8")

    (routes / "items.js").write_text("""
import express from 'express';
import { db } from '../db';

const router = express.Router();
export default router;
""", encoding="utf-8")

    (routes / "auth.js").write_text("""
import express from 'express';
import { db } from '../db';

const router = express.Router();
export default router;
""", encoding="utf-8")

    (server / "db.js").write_text("""
export const db = { users: [], items: [] };
""", encoding="utf-8")

    # Impact analysis on server/db.js: both items.js and auth.js depend on it!
    db_res = ast_tools.map_dependencies("server/db.js")
    assert "[DEPENDENCY IMPACT ANALYSIS: server/db.js]" in db_res
    assert "db" in db_res
    assert "server/routes/items.js" in db_res
    assert "server/routes/auth.js" in db_res


def test_map_dependencies_circular_dependency_detection(ast_tools, sandbox):
    (sandbox / "moduleA.js").write_text("import './moduleB';\nexport const A = 1;\n", encoding="utf-8")
    (sandbox / "moduleB.js").write_text("import './moduleA';\nexport const B = 2;\n", encoding="utf-8")

    res = ast_tools.map_dependencies()
    assert "CIRCULAR DEPENDENCIES DETECTED" in res
    assert "moduleA.js <---> moduleB.js" in res


def test_registry_map_dependencies_integration(registry, sandbox):
    (sandbox / "app.js").write_text("import './helper';\n", encoding="utf-8")
    (sandbox / "helper.js").write_text("export const h = 1;\n", encoding="utf-8")

    # Direct registry call
    res = registry.map_dependencies("helper.js")
    assert "app.js" in res

    # Dictionary dispatch call
    tools = registry.get_tools()
    assert "map_dependencies" in tools
    res2 = tools["map_dependencies"]("helper.js")
    assert res2 == res

    # In tool functions list
    tool_fns = registry.get_tool_functions()
    assert any(fn.__name__ == "map_dependencies" for fn in tool_fns)

    # In tool schemas list
    assert any(s.get("function", {}).get("name") == "map_dependencies" for s in TOOL_SCHEMAS)


def test_map_dependencies_argument_normalization():
    cases = [
        ({"path": "src/App.jsx"}, {"target_file": "src/App.jsx"}),
        ({"file_path": "src/App.jsx"}, {"target_file": "src/App.jsx"}),
        ({"file": "src/App.jsx"}, {"target_file": "src/App.jsx"}),
        ({"filename": "src/App.jsx"}, {"target_file": "src/App.jsx"}),
        ({"filepath": "src/App.jsx"}, {"target_file": "src/App.jsx"}),
    ]
    for inp, expected in cases:
        normalized = ToolArgumentNormalizer.normalize("map_dependencies", inp)
        assert normalized == expected


def test_map_dependencies_tag_parser():
    text = '<map_dependencies>{"target_file": "src/App.jsx"}</map_dependencies>'
    calls = ToolCallParser.extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["name"] == "map_dependencies"
    assert calls[0]["arguments"]["target_file"] == "src/App.jsx"


def test_map_dependencies_security_and_errors(ast_tools, sandbox):
    # Path traversal rejection
    res = ast_tools.map_dependencies("../secret.js")
    assert "Error: Access denied" in res

    # Nonexistent file
    res = ast_tools.map_dependencies("nonexistent.jsx")
    assert "Error: Target file does not exist" in res

    # Directory target
    (sandbox / "src").mkdir(exist_ok=True)
    res = ast_tools.map_dependencies("src")
    assert "Error: Target path is a directory" in res


def test_map_dependencies_python_project_graph(ast_tools, sandbox):
    backend = sandbox / "backend"
    models = backend / "models"
    models.mkdir(parents=True, exist_ok=True)

    (backend / "__init__.py").write_text("", encoding="utf-8")
    (models / "__init__.py").write_text("from .user import User\n__all__ = ['User']\n", encoding="utf-8")
    (models / "user.py").write_text("""
class User:
    def __init__(self, name: str):
        self.name = name
""", encoding="utf-8")

    (backend / "db.py").write_text("""
__all__ = ['engine', 'SessionLocal']
engine = 'sqlite:///:memory:'
SessionLocal = None
_internal = 123
""", encoding="utf-8")

    (backend / "app.py").write_text("""
from fastapi import FastAPI
from .db import engine, SessionLocal
from .models.user import User

app = FastAPI()

@app.get('/users')
async def get_users():
    return []
""", encoding="utf-8")

    # Impact analysis on db.py: app.py imports it!
    db_res = ast_tools.map_dependencies("backend/db.py")
    assert "[DEPENDENCY IMPACT ANALYSIS: backend/db.py]" in db_res
    assert "engine" in db_res
    assert "SessionLocal" in db_res
    assert "_internal" not in db_res
    assert "backend/app.py" in db_res

    # Impact analysis on user.py: app.py and models/__init__.py import it!
    user_res = ast_tools.map_dependencies("backend/models/user.py")
    assert "[DEPENDENCY IMPACT ANALYSIS: backend/models/user.py]" in user_res
    assert "User" in user_res
    assert "backend/app.py" in user_res
    assert "backend/models/__init__.py" in user_res

    # Impact analysis on app.py: imports db.py, models/user.py, external fastapi
    app_res = ast_tools.map_dependencies("backend/app.py")
    assert "[DEPENDENCY IMPACT ANALYSIS: backend/app.py]" in app_res
    assert "fastapi" in app_res
    assert "backend/db.py" in app_res
    assert "backend/models/user.py" in app_res
    assert "app" in app_res
    assert "get_users" in app_res


def test_map_dependencies_js_aliases_and_exports(ast_tools, sandbox):
    src = sandbox / "src"
    components = src / "components"
    components.mkdir(parents=True, exist_ok=True)

    (components / "Button.jsx").write_text("""
module.exports = { Button: () => null, icon: 'btn' };
exports.size = 'medium';
""", encoding="utf-8")

    (src / "App.jsx").write_text("""
import { Button } from '@/components/Button';
const Modal = () => import('./components/Button');
export async function fetchData() {}
export default async function App() {}
""", encoding="utf-8")

    app_res = ast_tools.map_dependencies("src/App.jsx")
    assert "src/components/Button.jsx" in app_res
    assert "fetchData" in app_res
    assert "default (App)" in app_res

    btn_res = ast_tools.map_dependencies("src/components/Button.jsx")
    assert "Button" in btn_res
    assert "icon" in btn_res
    assert "size" in btn_res
    assert "src/App.jsx" in btn_res


def test_map_dependencies_multi_node_cycle(ast_tools, sandbox):
    (sandbox / "A.js").write_text("import './B';\n", encoding="utf-8")
    (sandbox / "B.js").write_text("import './C';\n", encoding="utf-8")
    (sandbox / "C.js").write_text("import './A';\n", encoding="utf-8")

    res = ast_tools.map_dependencies()
    assert "CIRCULAR DEPENDENCIES DETECTED" in res
    assert "A.js -> B.js -> C.js -> A.js" in res


def test_map_dependencies_non_source_target(ast_tools, sandbox):
    src = sandbox / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "styles.css").write_text("body { color: red; }", encoding="utf-8")
    (src / "main.js").write_text("import './styles.css';\n", encoding="utf-8")

    res = ast_tools.map_dependencies("src/styles.css")
    assert "[DEPENDENCY IMPACT ANALYSIS: src/styles.css]" in res
    assert "NOTICE: 'src/styles.css' is not an AST-parseable source file" in res
    assert "src/main.js" in res
