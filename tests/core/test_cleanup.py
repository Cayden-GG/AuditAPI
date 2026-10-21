import pytest

import app.cleanup as cleanup


def populate(directory):
    directory.mkdir(parents=True)
    (directory / "file.pdf").write_bytes(b"x")
    (directory / "nested").mkdir()
    (directory / "nested" / "deep.json").write_text("{}")
    (directory / "link").symlink_to(directory / "file.pdf")


def test_service_cleanup_empties_results_and_logs(cleanup_sandbox):
    populate(cleanup_sandbox.results)
    populate(cleanup_sandbox.logs)

    cleanup.clean_up_service_files()

    assert list(cleanup_sandbox.results.iterdir()) == []
    assert list(cleanup_sandbox.logs.iterdir()) == []
    # the folders themselves stay
    assert cleanup_sandbox.results.exists() and cleanup_sandbox.logs.exists()


def test_service_cleanup_ignores_missing_directories(cleanup_sandbox):
    assert not cleanup_sandbox.results.exists()

    cleanup.clean_up_service_files()


def test_service_cleanup_does_not_follow_symlinks(cleanup_sandbox, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    cleanup_sandbox.results.mkdir()
    (cleanup_sandbox.results / "link").symlink_to(outside)

    cleanup.clean_up_service_files()

    assert (outside / "keep.txt").exists()
    assert not (cleanup_sandbox.results / "link").is_symlink()


def test_service_cleanup_keeps_going_when_one_item_cannot_be_deleted(cleanup_sandbox, monkeypatch, capsys):
    cleanup_sandbox.results.mkdir()
    (cleanup_sandbox.results / "stuck.pdf").write_bytes(b"x")
    (cleanup_sandbox.results / "fine.pdf").write_bytes(b"x")
    cleanup_sandbox.logs.mkdir()
    (cleanup_sandbox.logs / "log.jsonl").write_text("x")

    real_unlink = type(cleanup_sandbox.results).unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name == "stuck.pdf":
            raise PermissionError("busy")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(cleanup_sandbox.results), "unlink", flaky_unlink)

    cleanup.clean_up_service_files()

    assert (cleanup_sandbox.results / "stuck.pdf").exists()
    assert not (cleanup_sandbox.results / "fine.pdf").exists()
    assert not (cleanup_sandbox.logs / "log.jsonl").exists()
    assert "Error deleting" in capsys.readouterr().out


def test_system_cleanup_removes_lighthouse_temp_folders_only(cleanup_sandbox):
    (cleanup_sandbox.tmp / "lighthouse.abc123").mkdir()
    (cleanup_sandbox.tmp / "lighthouse.abc123" / "profile").write_text("x")
    (cleanup_sandbox.tmp / "lighthouse.def456").mkdir()
    (cleanup_sandbox.tmp / "other-folder").mkdir()
    (cleanup_sandbox.tmp / "lighthouse-report.html").write_text("x")

    cleanup.clean_up_system_files()

    assert sorted(p.name for p in cleanup_sandbox.tmp.iterdir()) == ["lighthouse-report.html", "other-folder"]


def test_system_cleanup_vacuums_the_journal(cleanup_sandbox):
    cleanup.clean_up_system_files()

    assert cleanup_sandbox.journal_calls == [["sudo", "journalctl", "--vacuum-time=1d"]]


def test_system_cleanup_survives_a_journal_failure(cleanup_sandbox, monkeypatch, capsys):
    def broken_run(cmd, **kwargs):
        raise FileNotFoundError("sudo")

    monkeypatch.setattr(cleanup.subprocess, "run", broken_run)

    cleanup.clean_up_system_files()

    assert "journalctl --vacuum failed" in capsys.readouterr().out


def test_full_cleanup_runs_both_cleanups(cleanup_sandbox):
    populate(cleanup_sandbox.results)
    (cleanup_sandbox.tmp / "lighthouse.abc").mkdir()

    cleanup.run_full_cleanup()

    assert list(cleanup_sandbox.results.iterdir()) == []
    assert list(cleanup_sandbox.tmp.iterdir()) == []
    assert len(cleanup_sandbox.journal_calls) == 1


@pytest.mark.parametrize("failing", ["clean_up_service_files", "clean_up_system_files"])
def test_full_cleanup_reraises_failures(cleanup_sandbox, monkeypatch, failing):
    def boom():
        raise OSError("disk gone")

    monkeypatch.setattr(cleanup, failing, boom)

    with pytest.raises(OSError, match="disk gone"):
        cleanup.run_full_cleanup()


def test_the_sandbox_points_away_from_the_real_machine(cleanup_sandbox):
    assert str(cleanup.RESULTS_DIR).startswith(str(cleanup_sandbox.results.parent))
    assert str(cleanup.LOGS_DIR).startswith(str(cleanup_sandbox.logs.parent))
    assert not str(cleanup.RESULTS_DIR).startswith("/var/www")
