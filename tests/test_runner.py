from pathlib import Path

from printguard.printers import QueueUnreadable, SimulatedPrinter
from printguard.state import FAILED, OK, SENT, StateStore

DAY = "2026-03-10"


def spool(config) -> Path:
    return config.out_dir / "spool"


def load(config):
    return StateStore(config.state_dir).load(DAY)


def test_happy_path_marks_ok_after_confirmation(config, make_runner, alert_file):
    assert make_runner().run() == 0
    state = load(config)
    assert state.status == OK
    assert state.job_id == "sim-1"
    assert not alert_file.exists()


def test_stuck_job_is_cancelled_and_marked_failed(config, make_runner, alert_file):
    printer = SimulatedPrinter(spool(config), stuck=True)
    assert make_runner(printer).run() == 1
    state = load(config)
    assert state.status == FAILED
    assert state.job_id is None
    assert "not confirmed" in state.error
    assert "queued" in alert_file.read_text()
    assert printer.printed_jobs() == []


def test_retry_after_stuck_job_prints_exactly_once(config, make_runner):
    make_runner(SimulatedPrinter(spool(config), stuck=True)).run()
    healthy = SimulatedPrinter(spool(config))
    assert make_runner(healthy).run() == 0
    assert healthy.printed_jobs() == ["sim-2"]
    assert load(config).status == OK


def test_unreadable_queue_after_submit_stays_sent(config, make_runner, alert_file):
    class FlakyPrinter(SimulatedPrinter):
        def status(self, job_id):
            raise QueueUnreadable("spooler service not responding")

    printer = FlakyPrinter(spool(config))
    assert make_runner(printer).run() == 1
    state = load(config)
    assert state.status == SENT
    assert state.job_id == "sim-1"
    assert "unverified" in alert_file.read_text()
    healthy = SimulatedPrinter(spool(config))
    assert make_runner(healthy).run() == 0
    assert load(config).status == OK
    assert len(healthy._load()) == 1


def test_reboot_between_submit_and_confirm_does_not_reprint(config, make_runner):
    class PowerCut(BaseException):
        pass

    class DiesWhileWaiting(SimulatedPrinter):
        def status(self, job_id):
            raise PowerCut

    try:
        make_runner(DiesWhileWaiting(spool(config))).run()
    except PowerCut:
        pass
    assert load(config).status == SENT

    after_reboot = SimulatedPrinter(spool(config))
    assert make_runner(after_reboot).run() == 0
    assert load(config).status == OK
    assert len(after_reboot._load()) == 1


def test_truncated_pdf_is_never_sent_to_the_printer(config, make_runner, alert_file):
    def truncating_render(rows, path, queried_at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n" + b"x" * 400)
        return path

    printer = SimulatedPrinter(spool(config))
    assert make_runner(printer, render=truncating_render).run() == 1
    assert load(config).status == FAILED
    assert "truncated" in alert_file.read_text()
    assert printer._load() == {}


def test_second_run_on_a_confirmed_day_does_not_print_again(config, make_runner):
    printer = SimulatedPrinter(spool(config))
    make_runner(printer).run()
    make_runner(printer).run()
    make_runner(printer).run()
    assert len(printer._load()) == 1


def test_print_only_reprints_without_touching_the_source(config, make_runner):
    printer = SimulatedPrinter(spool(config))
    make_runner(printer).run()

    def exploding_fetch(*_):
        raise AssertionError("source must not be queried")

    assert make_runner(printer, fetch=exploding_fetch).print_only() == 0
    assert len(printer._load()) == 2
    assert load(config).job_id == "sim-2"


def test_print_only_without_a_report_fails(config, make_runner, alert_file):
    assert make_runner().print_only() == 1
    assert "no report" in alert_file.read_text()


def test_print_only_rejects_a_pdf_damaged_after_the_fact(config, make_runner):
    printer = SimulatedPrinter(spool(config))
    make_runner(printer).run()
    pdf = Path(load(config).pdf)
    pdf.write_bytes(pdf.read_bytes()[:300])
    assert make_runner(printer).print_only() == 1
    assert len(printer._load()) == 1


def test_missing_database_fails_with_an_alert(config, make_runner, alert_file):
    config.db_path.unlink()
    assert make_runner().run() == 1
    assert "could not build report" in alert_file.read_text()


def test_corrupt_state_file_is_moved_aside(config, make_runner):
    store = StateStore(config.state_dir)
    config.state_dir.mkdir(parents=True)
    store.path(DAY).write_text("{not json", encoding="utf-8")
    assert make_runner().run() == 0
    assert store.path(DAY).with_suffix(".json.corrupt").exists()
