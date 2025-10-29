# src/services/cleanup_service.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_, delete, select

from src.database.models.user import User, UserStatus
from src.dependencies.database_session import DatabaseSession
from src.utils.logger_conf import logger


class UserCleanupService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
        self.setup_cleanup_jobs()

    def setup_cleanup_jobs(self):
        """Setup periodic cleanup jobs"""
        self.scheduler.add_job(
            func=self.cleanup_expired_users,
            trigger=CronTrigger(hour=2, minute=0),
            id="cleanup_expired_users",
            name="Clean up expired unverified users",
            replace_existing=True,
        )

        self.scheduler.add_job(
            func=self.send_verification_reminders,
            trigger=CronTrigger(hour=18, minute=0),
            id="send_verification_reminders",
            name="Send verification reminder emails",
            replace_existing=True,
        )

    async def cleanup_expired_users(self):
        """Clean up users with expired verification tokens"""
        try:
            current_time = datetime.now(ZoneInfo("UTC"))
            logger.info("Starting cleanup of expired unverified users...")

            async with DatabaseSession() as session:
                # Tìm users đã hết hạn verification và chưa verify
                result = await session.execute(
                    select(User).where(
                        and_(
                            User.status == UserStatus.PENDING_VERIFICATION,
                            User.email_verification_expires < current_time,
                            not User.email_verified,
                        )
                    )
                )
                expired_users = result.scalars().all()

                if not expired_users:
                    logger.info("No expired users to clean up")
                    return

                expired_count = len(expired_users)
                logger.info(f"Found {expired_count} expired users to clean up")

                # Log thông tin users sẽ bị xóa (cho debug)
                for user in expired_users:
                    logger.info(
                        f"Cleaning up user: {user.email} "
                        f"(expired: {user.email_verification_expires})"
                    )

                # Xóa các users đã hết hạn
                await session.execute(
                    delete(User).where(
                        and_(
                            User.status == UserStatus.PENDING_VERIFICATION,
                            User.email_verification_expires < current_time,
                            not User.email_verified,
                        )
                    )
                )

                await session.commit()
                logger.info(f"Successfully cleaned up {expired_count} expired users")

                return expired_count

        except Exception as e:
            logger.error(f"Error during user cleanup: {str(e)}")
            raise

    async def send_verification_reminders(self):
        """Send reminder emails to users whose verification will expire soon"""
        try:
            current_time = datetime.now(ZoneInfo("UTC"))
            reminder_threshold = current_time + timedelta(hours=24)
            logger.info("Checking for users needing verification reminders...")
            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(
                        and_(
                            User.status == UserStatus.PENDING_VERIFICATION,
                            User.email_verification_expires > current_time,
                            User.email_verification_expires <= reminder_threshold,
                            not User.email_verified,
                        )
                    )
                )
                users_needing_reminder = result.scalars().all()

                if not users_needing_reminder:
                    logger.info("No users need verification reminders")
                    return

                reminder_count = len(users_needing_reminder)
                logger.info(f"Sending verification reminders to {reminder_count} users")

                for user in users_needing_reminder:
                    await self._send_reminder_email(user)

                logger.info(f"Successfully sent {reminder_count} reminder emails")
                return reminder_count

        except Exception as e:
            logger.error(f"Error sending verification reminders: {str(e)}")
            raise

    async def _send_reminder_email(self, user: User):
        """Send reminder email to user"""
        try:
            # TODO: Integrate with your GmailAPI here
            logger.info(f"Reminder email sent to {user.email}")
            # Example:
            # subject = "Don't forget to verify your email"
            # body = f"Hi {user.full_name}, your verification link expires soon..."
            # await gmail_api.send_message(user.email, subject, body)

        except Exception as e:
            logger.error(f"Failed to send reminder email to {user.email}: {str(e)}")

    async def manual_cleanup(self, dry_run: bool = True):
        """Manual cleanup for testing/admin purposes"""
        try:
            current_time = datetime.now(ZoneInfo("UTC"))

            async with DatabaseSession() as session:
                result = await session.execute(
                    select(User).where(
                        and_(
                            User.status == UserStatus.PENDING_VERIFICATION,
                            User.email_verification_expires < current_time,
                            not User.email_verified,
                        )
                    )
                )
                expired_users = result.scalars().all()

                if dry_run:
                    logger.info(f"DRY RUN: Would clean up {len(expired_users)} users:")
                    for user in expired_users:
                        logger.info(
                            f"  - {user.email} (expired: {user.email_verification_expires})"
                        )
                    return len(expired_users)
                else:
                    return await self.cleanup_expired_users()

        except Exception as e:
            logger.error(f"Error during manual cleanup: {str(e)}")
            raise

    def start_scheduler(self):
        """Start the cleanup scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("User cleanup scheduler started")

    def stop_scheduler(self):
        """Stop the cleanup scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("User cleanup scheduler stopped")


cleanup_service = UserCleanupService()
