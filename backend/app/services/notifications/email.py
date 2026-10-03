import logging
import smtplib
from email.message import EmailMessage

from app.core.config import EmailConfig, settings
from app.services.alerts import SEVERITY_RANK
from app.services.faces.storage import resolve
from app.services.notifications.base import NotificationChannel

logger = logging.getLogger(__name__)

TYPE_TITLES = {
    "unknown_person": "Unknown person",
    "restricted_area": "Person in restricted area",
    "suspicious_activity": "Suspicious activity",
    "camera_offline": "Camera offline",
}


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, config: EmailConfig):
        self.config = config

    def wants(self, alert: dict) -> bool:
        threshold = SEVERITY_RANK.get(self.config.min_severity, SEVERITY_RANK["high"])
        return SEVERITY_RANK.get(alert["severity"], 0) >= threshold

    def build_message(self, alert: dict, snapshot_path: str | None) -> EmailMessage:
        cfg = self.config
        title = TYPE_TITLES.get(alert["type"], alert["type"])
        message = EmailMessage()
        message["Subject"] = f"{cfg.subject_prefix} {alert['severity'].upper()}: {title} — {alert.get('camera_name', alert['camera_id'])}"
        message["From"] = cfg.from_addr or cfg.username
        message["To"] = ", ".join(cfg.to_addrs)
        lines = [
            alert["message"],
            "",
            f"Camera:   {alert.get('camera_name', alert['camera_id'])}",
            f"Severity: {alert['severity']}",
            f"Time:     {alert['created_at']} (UTC)",
        ]
        for key, value in (alert.get("details") or {}).items():
            lines.append(f"{key.replace('_', ' ').capitalize()}: {value}")
        if settings.public_url:
            lines += ["", f"Open the dashboard: {settings.public_url.rstrip('/')}/alerts"]
        lines += ["", "You are receiving this because email notifications are enabled for this system."]
        message.set_content("\n".join(lines))

        if cfg.attach_snapshot and snapshot_path:
            path = resolve(snapshot_path)
            if path.is_file():
                message.add_attachment(path.read_bytes(), maintype="image", subtype="jpeg", filename="snapshot.jpg")
        return message

    def send(self, alert: dict, snapshot_path: str | None) -> None:
        cfg = self.config
        message = self.build_message(alert, snapshot_path)
        smtp_class = smtplib.SMTP_SSL if cfg.use_ssl else smtplib.SMTP
        with smtp_class(cfg.host, cfg.port, timeout=cfg.timeout_seconds) as smtp:
            if cfg.use_starttls and not cfg.use_ssl:
                smtp.starttls()
            if cfg.username:
                smtp.login(cfg.username, cfg.password)
            smtp.send_message(message)
        logger.info("Email sent for alert #%s to %d recipient(s)", alert["id"], len(cfg.to_addrs))

    def send_test(self) -> None:
        """Send a harmless test message (used by the 'send test email' button)."""
        self.send(
            {
                "id": 0,
                "type": "camera_offline",
                "severity": self.config.min_severity,
                "camera_id": "test",
                "camera_name": "Test camera",
                "message": "This is a test notification from Smart CCTV.",
                "created_at": "now",
                "details": {},
            },
            None,
        )
