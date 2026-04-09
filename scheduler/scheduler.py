import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db.database import Database
from core.agent_manager import AgentManager

logger = logging.getLogger(__name__)

class AgScheduler:
    def __init__(self, db: Database, agent_manager: AgentManager):
        self.db = db
        self.manager = agent_manager
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[int, str] = {}

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
        if task_id in self._jobs:
            try:
                self._scheduler.remove_job(self._jobs[task_id])
            except Exception:
                pass
            del self._jobs[task_id]
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
