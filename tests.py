"""Unit tests for the assistant package."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import Config
from memory import Memory
from tools import (
    analyze_csv,
    call_tool,
    check_connectivity,
    checksum_file,
    compress_files,
    copy_path,
    create_task,
    delete_file,
    describe_data,
    disk_usage,
    dns_lookup,
    extract_archive,
    format_report,
    generate_password,
    get_env_vars,
    hash_text,
    list_directory,
    list_tools,
    move_path,
    read_file,
    run_python,
    search_files,
    set_env_var,
    sqlite_export_csv,
    sqlite_query,
    summarize_expenses,
    summarize_text,
    system_info,
    word_frequency,
    write_file,
)


# ── Config ────────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.model, "gpt-4o")
        self.assertGreater(cfg.max_tokens, 0)
        self.assertGreater(cfg.max_iterations, 0)

    def test_env_override(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "ASSISTANT_MODEL": "gpt-3.5-turbo"}):
            cfg = Config.load()
        self.assertEqual(cfg.api_key, "test-key")
        self.assertEqual(cfg.model, "gpt-3.5-turbo")

    def test_save_load_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tmp = Path(tf.name)
        try:
            cfg = Config()
            cfg.model = "gpt-test-model"
            cfg.save(tmp)
            loaded = Config.load(tmp)
            self.assertEqual(loaded.model, "gpt-test-model")
        finally:
            tmp.unlink(missing_ok=True)


# ── Memory ────────────────────────────────────────────────────────────────

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.write(b"[]")
        self.tmp.close()
        self.cfg = Config()
        self.cfg.memory_path = self.tmp.name
        self.mem = Memory(self.cfg)

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_store_and_retrieve(self):
        entry_id = self.mem.store("Python is awesome", entry_type="fact", tags=["python"])
        self.assertIsNotNone(entry_id)
        entry = self.mem.get(entry_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["content"], "Python is awesome")
        self.assertIn("python", entry["tags"])

    def test_search(self):
        self.mem.store("Machine learning is fascinating")
        self.mem.store("Deep learning uses neural networks")
        results = self.mem.search("learning")
        self.assertEqual(len(results), 2)

    def test_search_no_match(self):
        self.mem.store("Unrelated content")
        results = self.mem.search("quantum physics")
        self.assertEqual(len(results), 0)

    def test_delete(self):
        entry_id = self.mem.store("To be deleted")
        self.assertTrue(self.mem.delete(entry_id))
        self.assertIsNone(self.mem.get(entry_id))

    def test_update(self):
        entry_id = self.mem.store("Original content")
        self.mem.update(entry_id, content="Updated content")
        entry = self.mem.get(entry_id)
        self.assertEqual(entry["content"], "Updated content")

    def test_link_entries(self):
        id1 = self.mem.store("Fact A")
        id2 = self.mem.store("Fact B")
        self.assertTrue(self.mem.link_entries(id1, id2, "relates_to"))
        links = self.mem.get_links(id1)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["target"], id2)

    def test_stats(self):
        self.mem.store("fact one", entry_type="fact")
        self.mem.store("goal one", entry_type="goal")
        stats = self.mem.stats()
        self.assertEqual(stats["total"], 2)
        self.assertIn("fact", stats["by_type"])
        self.assertIn("goal", stats["by_type"])

    def test_persistence(self):
        self.mem.store("persisted content")
        # Reload from disk
        mem2 = Memory(self.cfg)
        results = mem2.search("persisted")
        self.assertEqual(len(results), 1)


# ── Tools: System ─────────────────────────────────────────────────────────

class TestSystemTools(unittest.TestCase):
    def test_system_info(self):
        result = system_info()
        self.assertEqual(result["status"], "ok")
        self.assertIn("os", result["result"])
        self.assertIn("hostname", result["result"])

    def test_get_env_vars(self):
        result = get_env_vars()
        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["result"], dict)

    def test_get_env_vars_prefix(self):
        with patch.dict(os.environ, {"TEST_FOO": "bar", "PATH": "/usr/bin"}):
            result = get_env_vars(prefix="TEST_")
        self.assertEqual(result["status"], "ok")
        self.assertIn("TEST_FOO", result["result"])
        self.assertNotIn("PATH", result["result"])

    def test_set_env_var(self):
        result = set_env_var("_ASSISTANT_TEST_VAR", "hello")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(os.environ.get("_ASSISTANT_TEST_VAR"), "hello")
        del os.environ["_ASSISTANT_TEST_VAR"]


# ── Tools: Files ─────────────────────────────────────────────────────────

class TestFileTools(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name: str) -> str:
        return str(Path(self.tmpdir) / name)

    def test_write_and_read_file(self):
        p = self._path("test.txt")
        r = write_file(p, "hello world")
        self.assertEqual(r["status"], "ok")
        r2 = read_file(p)
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["result"]["content"], "hello world")

    def test_read_nonexistent(self):
        r = read_file(self._path("nope.txt"))
        self.assertEqual(r["status"], "error")

    def test_append_file(self):
        p = self._path("append.txt")
        write_file(p, "line1\n")
        write_file(p, "line2\n", append=True)
        r = read_file(p)
        self.assertIn("line1", r["result"]["content"])
        self.assertIn("line2", r["result"]["content"])

    def test_delete_file(self):
        p = self._path("del.txt")
        write_file(p, "bye")
        r = delete_file(p)
        self.assertEqual(r["status"], "ok")
        self.assertFalse(Path(p).exists())

    def test_copy_path(self):
        src = self._path("src.txt")
        dst = self._path("dst.txt")
        write_file(src, "copy me")
        r = copy_path(src, dst)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(Path(dst).exists())

    def test_move_path(self):
        src = self._path("move_src.txt")
        dst = self._path("move_dst.txt")
        write_file(src, "move me")
        r = move_path(src, dst)
        self.assertEqual(r["status"], "ok")
        self.assertFalse(Path(src).exists())
        self.assertTrue(Path(dst).exists())

    def test_search_files(self):
        write_file(self._path("a.py"), "pass")
        write_file(self._path("b.txt"), "hello")
        r = search_files(self.tmpdir, pattern="*.py")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["count"], 1)
        self.assertTrue(r["result"]["matches"][0].endswith(".py"))

    def test_search_files_contains(self):
        write_file(self._path("c.txt"), "secret content here")
        write_file(self._path("d.txt"), "nothing special")
        r = search_files(self.tmpdir, contains="secret content")
        self.assertEqual(r["result"]["count"], 1)

    def test_list_directory(self):
        write_file(self._path("visible.txt"), "v")
        r = list_directory(self.tmpdir)
        self.assertEqual(r["status"], "ok")
        names = [e["name"] for e in r["result"]]
        self.assertIn("visible.txt", names)

    def test_compress_and_extract(self):
        src = self._path("compress_me.txt")
        write_file(src, "compressed content")
        arc = self._path("test.zip")
        r = compress_files([src], arc)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(Path(arc).exists())

        out_dir = self._path("extracted")
        r2 = extract_archive(arc, out_dir)
        self.assertEqual(r2["status"], "ok")

    def test_checksum_file(self):
        p = self._path("hash_me.txt")
        write_file(p, "deterministic content")
        r = checksum_file(p)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(r["result"]["sha256"]), 64)

    def test_disk_usage(self):
        r = disk_usage(self.tmpdir)
        self.assertEqual(r["status"], "ok")
        self.assertIn("total_gb", r["result"])

    def test_analyze_csv(self):
        p = self._path("data.csv")
        write_file(p, "name,age,score\nAlice,30,95\nBob,25,87\n")
        r = analyze_csv(p)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["rows"], 2)
        self.assertEqual(r["result"]["columns"], 3)


# ── Tools: Network ────────────────────────────────────────────────────────

class TestNetworkTools(unittest.TestCase):
    def test_check_connectivity_returns_dict(self):
        r = check_connectivity()
        self.assertIn("connected", r["result"])

    def test_dns_lookup_valid(self):
        r = dns_lookup("localhost")
        self.assertEqual(r["status"], "ok")
        self.assertIn("addresses", r["result"])

    def test_dns_lookup_invalid(self):
        r = dns_lookup("this.definitely.does.not.exist.invalid")
        self.assertEqual(r["status"], "error")


# ── Tools: Security ───────────────────────────────────────────────────────

class TestSecurityTools(unittest.TestCase):
    def test_generate_password_length(self):
        r = generate_password(length=32)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(r["result"]["password"]), 32)

    def test_generate_password_no_symbols(self):
        r = generate_password(length=16, include_symbols=False)
        pwd = r["result"]["password"]
        import string
        for ch in pwd:
            self.assertIn(ch, string.ascii_letters + string.digits)

    def test_hash_text_sha256(self):
        r = hash_text("hello", "sha256")
        self.assertEqual(
            r["result"]["hash"],
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        )

    def test_hash_text_md5(self):
        r = hash_text("hello", "md5")
        self.assertEqual(r["result"]["hash"], "5d41402abc4b2a76b9719d911017c592")

    def test_check_file_permissions(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tmp = tf.name
        try:
            from tools import check_file_permissions
            r = check_file_permissions(tmp)
            self.assertEqual(r["status"], "ok")
            self.assertIn("mode", r["result"])
        finally:
            Path(tmp).unlink(missing_ok=True)


# ── Tools: Programming ────────────────────────────────────────────────────

class TestProgrammingTools(unittest.TestCase):
    def test_run_python_basic(self):
        r = run_python("print('hello')")
        self.assertEqual(r["status"], "ok")
        self.assertIn("hello", r["result"]["stdout"])

    def test_run_python_error(self):
        r = run_python("raise ValueError('oops')")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["status"], "error")
        self.assertIn("ValueError", r["result"]["stderr"])

    def test_run_python_arithmetic(self):
        r = run_python("x = 2 ** 10\nprint(x)")
        self.assertIn("1024", r["result"]["stdout"])

    def test_lint_python_valid(self):
        from tools import lint_python
        r = lint_python("x = 1\nprint(x)\n")
        self.assertEqual(r["status"], "ok")

    def test_lint_python_invalid(self):
        from tools import lint_python
        r = lint_python("def broken(\n    pass\n")
        self.assertEqual(r["status"], "ok")
        self.assertGreater(r["result"]["issues"], 0)


# ── Tools: Databases ─────────────────────────────────────────────────────

class TestDatabaseTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = self.tmp.name
        # Create a test table
        sqlite_query(self.db, "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, value REAL)")
        sqlite_query(self.db, "INSERT INTO items (name, value) VALUES (?, ?)", ["apple", 1.5])
        sqlite_query(self.db, "INSERT INTO items (name, value) VALUES (?, ?)", ["banana", 2.0])

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_select(self):
        r = sqlite_query(self.db, "SELECT * FROM items ORDER BY id")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["count"], 2)
        self.assertEqual(r["result"]["rows"][0]["name"], "apple")

    def test_insert(self):
        r = sqlite_query(self.db, "INSERT INTO items (name, value) VALUES (?, ?)", ["cherry", 3.0])
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["affected_rows"], 1)

    def test_export_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            out = tf.name
        try:
            r = sqlite_export_csv(self.db, "items", out)
            self.assertEqual(r["status"], "ok")
            self.assertEqual(r["result"]["rows_exported"], 2)
            content = Path(out).read_text()
            self.assertIn("apple", content)
        finally:
            Path(out).unlink(missing_ok=True)


# ── Tools: Data analysis ─────────────────────────────────────────────────

class TestDataTools(unittest.TestCase):
    def test_describe_data(self):
        r = describe_data([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["result"]["mean"], 3.0)
        self.assertEqual(r["result"]["min"], 1.0)
        self.assertEqual(r["result"]["max"], 5.0)

    def test_describe_data_empty(self):
        r = describe_data([])
        self.assertEqual(r["status"], "error")

    def test_summarize_expenses(self):
        expenses = [
            {"amount": 50, "category": "food"},
            {"amount": 30, "category": "transport"},
            {"amount": 20, "category": "food"},
        ]
        r = summarize_expenses(expenses)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["by_category"]["food"], 70.0)
        self.assertEqual(r["result"]["total"], 100.0)


# ── Tools: Productivity ───────────────────────────────────────────────────

class TestProductivityTools(unittest.TestCase):
    def test_create_task(self):
        r = create_task("Write docs", priority="high", project="myproject")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["title"], "Write docs")
        self.assertEqual(r["result"]["priority"], "high")
        self.assertFalse(r["result"]["done"])

    def test_format_report_list(self):
        data = [{"name": "Alice", "score": 95}, {"name": "Bob", "score": 87}]
        r = format_report(data, title="Scores")
        self.assertEqual(r["status"], "ok")
        self.assertIn("# Scores", r["result"])
        self.assertIn("Alice", r["result"])

    def test_format_report_dict(self):
        r = format_report({"key": "value"}, title="Test")
        self.assertIn("**key**", r["result"])


# ── Tools: Research ───────────────────────────────────────────────────────

class TestResearchTools(unittest.TestCase):
    def test_summarize_text(self):
        text = (
            "Artificial intelligence is transforming the world. "
            "It enables machines to perform human-like tasks. "
            "Deep learning is a subset of machine learning. "
            "Neural networks power modern AI systems. "
            "The field is advancing rapidly every year."
        )
        r = summarize_text(text, max_sentences=3)
        self.assertEqual(r["status"], "ok")
        self.assertGreater(len(r["result"]["summary"]), 0)

    def test_word_frequency(self):
        text = "the cat sat on the mat the cat"
        r = word_frequency(text, top_n=5)
        self.assertEqual(r["status"], "ok")
        # 'cat' should appear twice
        self.assertIn("cat", r["result"])

    def test_word_frequency_excludes_stopwords(self):
        text = "the the the and and for"
        r = word_frequency(text, top_n=10)
        # All are stopwords; result should be empty or minimal
        self.assertEqual(r["status"], "ok")


# ── Tool registry ─────────────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):
    def test_list_tools_not_empty(self):
        tools = list_tools()
        self.assertGreater(len(tools), 0)

    def test_all_tools_have_required_fields(self):
        for t in list_tools():
            self.assertIn("name", t)
            self.assertIn("category", t)
            self.assertIn("description", t)

    def test_call_unknown_tool(self):
        from tools import call_tool
        with self.assertRaises(ValueError):
            call_tool("nonexistent_tool_xyz", {})

    def test_get_schemas_returns_openai_format(self):
        from tools import get_schemas
        schemas = get_schemas()
        for s in schemas:
            self.assertIn("type", s)
            self.assertEqual(s["type"], "function")
            self.assertIn("function", s)
            self.assertIn("name", s["function"])
            self.assertIn("parameters", s["function"])


# ── Assistant (mocked) ────────────────────────────────────────────────────

class TestAssistant(unittest.TestCase):
    def _make_assistant(self, responses: list[str]) -> "Assistant":
        from assistant import Assistant
        cfg = Config()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            cfg.memory_path = tf.name
            tf.write(b"[]")
        cfg.require_approval = False
        assistant = Assistant(cfg)

        client_mock = MagicMock()
        idx = {"i": 0}

        def fake_chat(messages, tools=None, tool_choice="auto", stream=False):
            text = responses[min(idx["i"], len(responses) - 1)]
            idx["i"] += 1
            return {
                "choices": [{"message": {"role": "assistant", "content": text},
                              "finish_reason": "stop"}],
                "model": "mock",
            }

        client_mock.chat.side_effect = fake_chat
        assistant.client = client_mock
        return assistant

    def test_basic_chat(self):
        from assistant import Assistant
        assistant = self._make_assistant(["Hello! How can I help?"])
        response = assistant.chat("Hi there")
        self.assertEqual(response, "Hello! How can I help?")

    def test_history_grows(self):
        from assistant import Assistant
        assistant = self._make_assistant(["Response 1", "Response 2"])
        assistant.chat("Message 1")
        assistant.chat("Message 2")
        # 2 user + 2 assistant messages
        self.assertEqual(len(assistant.history), 4)

    def test_reset_clears_history(self):
        from assistant import Assistant
        assistant = self._make_assistant(["ok"])
        assistant.chat("hello")
        assistant.reset()
        self.assertEqual(len(assistant.history), 0)

    def test_available_tools(self):
        from assistant import Assistant
        assistant = self._make_assistant([])
        tools = assistant.available_tools()
        self.assertGreater(len(tools), 0)

    def test_memory_integration(self):
        from assistant import Assistant
        assistant = self._make_assistant(["I'll remember that."])
        entry_id = assistant.remember("Important fact about testing", entry_type="fact")
        self.assertIsNotNone(entry_id)
        results = assistant.recall("testing")
        self.assertGreater(len(results), 0)
        try:
            Path(assistant.memory.path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_ambiguous_performance_request_is_clarified_without_api_call(self):
        assistant = self._make_assistant(["This should not be used."])
        response = assistant.chat("Make my project faster")
        self.assertIn("startup", response)
        self.assertIn("runtime", response)
        assistant.client.chat.assert_not_called()

    def test_ambiguous_deletion_request_is_clarified_without_api_call(self):
        assistant = self._make_assistant(["This should not be used."])
        response = assistant.chat("delete everything")
        self.assertIn("build artifacts", response)
        self.assertIn("git-ignored files", response)
        assistant.client.chat.assert_not_called()

    def test_private_key_exposure_is_refused_without_api_call(self):
        assistant = self._make_assistant(["This should not be used."])
        response = assistant.chat("Expose my SSH key online")
        self.assertIn("can't expose", response)
        assistant.client.chat.assert_not_called()

    def test_root_deletion_tool_call_is_blocked(self):
        assistant = self._make_assistant([])
        result = assistant._execute_tool({
            "function": {"name": "run_command", "arguments": '{"command": "rm -rf /"}'},
        })
        self.assertEqual(result["status"], "blocked")

    def test_operational_playbooks_are_in_system_prompt(self):
        from assistant import SYSTEM_PROMPT
        self.assertIn("git reflog", SYSTEM_PROMPT)
        self.assertIn("package.json", SYSTEM_PROMPT)
        self.assertIn("cargo flamegraph", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
