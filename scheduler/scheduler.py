import logging
from dataclasses import dataclass, field
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db.database import Database
from core.agent_manager import AgentManager

logger = logging.getLogger(__name__)


@dataclass
class ReloadReport:
    added: list[int] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.updated)


class AgScheduler:
    def __init__(self, db: Database, agent_manager: AgentManager):
        self.db = db
        self.manager = agent_manager
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[int, str] = {}
        self._live_tasks: dict[int, dict] = {}

    async def start(self):
        tasks = await self.list_tasks()
        for task in tasks:
            if task["enabled"]:
                self._register_job(task)
        self._scheduler.start()
        logger.info(f"Scheduler started with {len(tasks)} tasks")

    def stop(self):
        self._scheduler.shutdown(wait=False)

    async def add_task(self, cron_expression: str, agent_name: str, prompt: str) -> int:
        task_id = await self.db.execute(
            "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
            (cron_expression, agent_name, prompt),
        )
        task = await self.db.fetch_one("SELECT * FROM schedule WHERE id = ?", (task_id,))
        if self._scheduler.running:
            self._register_job(task)
        return task_id

    async def remove_task(self, task_id: int) -> None:
        self._unregister_job(task_id)
        await self.db.execute("DELETE FROM schedule WHERE id = ?", (task_id,))

    async def toggle_task(self, task_id: int, enabled: bool) -> None:
        await self.db.execute(
            "UPDATE schedule SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, task_id),
        )

    async def list_tasks(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM schedule ORDER BY id")

    async def run_now(self, task_id: int) -> None:
        task = await self.db.fetch_one("SELECT * FROM schedule WHERE id = ?", (task_id,))
        if task:
            await self._execute_task(task)

    def _register_job(self, task: dict):
        parts = task["cron_expression"].split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        job = self._scheduler.add_job(
            self._execute_task, trigger, args=[task], id=f"task-{task['id']}"
        )
        self._jobs[task["id"]] = job.id
        self._live_tasks[task["id"]] = {
            "cron_expression": task["cron_expression"],
            "agent_name": task["agent_name"],
            "prompt": task["prompt"],
        }

    def _unregister_job(self, task_id: int) -> None:
        job_id = self._jobs.pop(task_id, None)
        self._live_tasks.pop(task_id, None)
        if job_id is not None:
            try:
                self._scheduler.remove_job(job_id)
            except Exception as e:
                logger.debug("remove_job(%s) ignored: %s", job_id, e)

    def _task_differs(self, task_id: int, db_task: dict) -> bool:
        live = self._live_tasks.get(task_id)
        if live is None:
            return True
        return (
            live["cron_expression"] != db_task["cron_expression"]
            or live["agent_name"] != db_task["agent_name"]
            or live["prompt"] != db_task["prompt"]
        )

    async def reload_from_db(self) -> ReloadReport:
        """Идемпотентная синхронизация живых задач с таблицей schedule.

        Вызывается из main.py по SIGUSR1 (Unix) или файл-флагу (Windows)
        когда CLI добавил/удалил/изменил запись в БД. Безопасно звать сколько
        угодно раз: метод diff'ит текущее состояние и применяет только
        реальные различия.
        """
        db_rows = await self.list_tasks()
        db_tasks = {t["id"]: t for t in db_rows if t.get("enabled")}
        live_ids = set(self._jobs.keys())
        db_ids = set(db_tasks.keys())
        report = ReloadReport()
        for tid in sorted(db_ids - live_ids):
            self._register_job(db_tasks[tid])
            report.added.append(tid)
        for tid in sorted(live_ids - db_ids):
            self._unregister_job(tid)
            report.removed.append(tid)
        for tid in sorted(db_ids & live_ids):
            if self._task_differs(tid, db_tasks[tid]):
                self._unregister_job(tid)
                self._register_job(db_tasks[tid])
                report.updated.append(tid)
        if report.changed:
            logger.info(
                "Schedule reloaded: +%d -%d ~%d",
                len(report.added), len(report.removed), len(report.updated),
            )
        return report

    async def _execute_task(self, task: dict):
        agent_name = task["agent_name"]
        prompt = task["prompt"]
        try:
            agent = await self.manager.get_agent(agent_name)
            if not agent:
                logger.warning(f"Scheduled task {task['id']}: agent '{agent_name}' not found")
                await self._update_result(task["id"], "error")
                return
            await self.manager.send_prompt(agent_name, prompt)
            await self._update_result(task["id"], "success")
        except Exception as e:
            logger.error(f"Scheduled task {task['id']} failed: {e}")
            await self._update_result(task["id"], "error")

    async def _update_result(self, task_id: int, result: str):
        await self.db.execute(
            "UPDATE schedule SET last_run = ?, last_result = ? WHERE id = ?",
            (datetime.now().isoformat(), result, task_id),
        )
