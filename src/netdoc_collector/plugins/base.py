"""
Base class for all vendor/platform plugins.

Every plugin must implement:
  - commands()   -> list of CLI commands to run on the device
  - parse()      -> transform raw command outputs into a structured dict
  - to_yaml_dict() -> return the final dict to be serialized into YAML output
"""

from abc import ABC, abstractmethod
import logging
import re
import json
from typing import Any
from pathlib import Path
from textfsm.parser import TextFSMError
from nornir.core.task import Task
from nornir_netmiko.tasks import netmiko_send_command
from netmiko.utilities import get_structured_data
from netmiko.exceptions import NetmikoTimeoutException
from netdoc_sdk.models import RawOutput

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    def __init__(
        self,
        host_name: str,
        host_data: dict,
        report_path: Path | None,
        claim_token: str | None = None,
        client=None,
        idempotency_key: str | None = None,
        job_id: str | None = None,
    ):
        """
        Args:
            host_name: Nornir host name (used as key in output)
            host_data: dict of host.data fields from inventory (vendor, site, etc.)
        """
        self.report_path = None
        self.host_name: str = host_name
        self.host_data: dict = host_data
        self.claim_token: str | None = claim_token
        self.client = client
        self.job_id: str | None = job_id
        self.idempotency_key: str | None = idempotency_key

        if report_path:
            # Save report path to save logs locally
            self.report_path = report_path / Path(host_name)
            self.report_path.mkdir(exist_ok=True, parents=True)

    def upload_raw_outputs(self, raw_outputs):
        errors = []
        if self.client:
            logging.info(f"Uploading collected data")
            self.client.discovery_jobs_raw_outputs_create(data=raw_outputs, claim_token=self.claim_token)
        return errors

    @abstractmethod
    def collect(self, task: Task) -> dict[str, Any]:
        """Collect data from devices and return result in NetDoc format."""
        ...

    # @abstractmethod
    # def to_netdoc_dict(self, parsed_outputs: dict[str, Any]) -> dict[str, Any]:
    #     """
    #     Build the finalNetDoc dict for this host.

    #     Args:
    #         parsed_outputs: output of parse()

    #     Returns:
    #         Dict that will be written under this host's key in the output YAML.
    #     """
    #     ...

    # @abstractmethod
    # def to_netdok_obj(
    #     self,
    #     parsed_outputs: dict[str, Any],
    #     raw_outputs: dict[str, str] | None = None,
    # ) -> RawOutput:
    #     """
    #     Build the DeviceData object for this host.

    #     Args:
    #         parsed_outputs: dictionary produced from the device config
    #         raw_outputs: raw command outputs from the device

    #     Returns:
    #         Object that will be persisted in the DB
    #     """
    #     ...

    @staticmethod
    def slugify(text: str):
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        text = re.sub(r'^-+|-+$', '', text)
        return text

    # @staticmethod
    # def first_record(records: Any) -> dict[str, Any]:
    #     if isinstance(records, list) and records and isinstance(records[0], dict):
    #         return records[0]
    #     return {}

    # @staticmethod
    # def safe_int(value: Any, default: int | None = None) -> int | None:
    #     if value is None or value == '':
    #         return default
    #     try:
    #         return int(str(value).strip())
    #     except (TypeError, ValueError):
    #         return default

    # @staticmethod
    # def safe_model(model_cls: Any, **kwargs: Any) -> Any | None:
    #     try:
    #         return model_cls(**kwargs)
    #     except Exception as exc:
    #         logger.debug('Skipping invalid %s data: %s', model_cls.__name__, exc)
    #         return None

    # @classmethod
    # def expand_vlan_ids(cls, value: Any) -> list[int]:
    #     vlan_ids: set[int] = set()

    #     if isinstance(value, list):
    #         for item in value:
    #             vlan_ids.update(cls.expand_vlan_ids(item))
    #         return sorted(vlan_ids)

    #     if isinstance(value, int):
    #         return [value] if 1 <= value <= 4094 else []

    #     if not isinstance(value, str):
    #         return []

    #     for token in value.replace(' ', '').split(','):
    #         if not token or token.lower() in {'none', 'all'}:
    #             continue
    #         if '-' in token:
    #             start, end = token.split('-', 1)
    #             start_id = cls.safe_int(start)
    #             end_id = cls.safe_int(end)
    #             if start_id is None or end_id is None or start_id > end_id:
    #                 continue
    #             vlan_ids.update(range(max(start_id, 1), min(end_id, 4094) + 1))
    #             continue

    #         vlan_id = cls.safe_int(token)
    #         if vlan_id is not None and 1 <= vlan_id <= 4094:
    #             vlan_ids.add(vlan_id)

    #     return sorted(vlan_ids)

    @staticmethod
    def parse_netmiko_output(raw_output, platform, cmd) -> None | list:
        try:
            parsed_output: list = get_structured_data(raw_output, platform=platform, command=cmd)
            if isinstance(parsed_output, list):
                # Valid output is a list
                return parsed_output
        except TextFSMError:
            pass
        return None

    def write_output(self, content, log) -> None:
        if not self.report_path:
            # Write output if report path is set only
            return
        if not content:
            # Skipping empty content
            return

        log_file = self.slugify(log)
        if isinstance(content, dict) or isinstance(content, list):
            # Write a JSON file
            with open(self.report_path / Path(f'{log_file}.json'), 'w', encoding='utf-8') as fh:
                json.dump(content, fh, indent=2)
            return

        # Write a RAW content
        with open(self.report_path / Path(f'{log_file}.raw'), 'w') as fh:
            fh.write(content)

    def run_netmiko_cmd(self, task: Task, platform, cmd) -> tuple[str, None | list]:
        errors = []
        try:
            parsed_output = None
            cmd_result: str = task.run(
                task=netmiko_send_command,
                command_string=cmd,
                read_timeout=240,  # TODO - should use the cmd-timeout argument here
                use_textfsm=False,
            )
            logger.debug(f"Raw output for command '{cmd}' on {self.host_name}: {cmd_result.result}")
        except Exception as e:
            self.write_output(f"Error running command: {e}", cmd)
            logger.error(f"Error running command '{cmd}' on {self.host_name}: {e}")
            raise Exception(f"Error running command '{cmd}' on {self.host_name}: {e}")

        try:
            raw_output = cmd_result.result
            parsed_output = self.parse_netmiko_output(raw_output, platform, cmd)
        except Exception as e:
            self.write_output(f"Error parsing command '{cmd}' output on {self.host_name}: {e}", cmd)
            logger.error(f"Error parsing command '{cmd}' output on {self.host_name}: {e}")

        # Dump output files
        self.write_output(raw_output, cmd)
        self.write_output(parsed_output, cmd)

        return raw_output, parsed_output, errors

    # @classmethod
    # def _speed_to_mbps(cls, *values: Any) -> int | None:
    #     for value in values:
    #         if not value:
    #             continue
    #         value_text = str(value).strip().lower()
    #         match = re.search(r'(\d+(?:\.\d+)?)', value_text)
    #         if not match:
    #             continue

    #         speed = float(match.group(1))
    #         if 'gb' in value_text or 'gbit' in value_text:
    #             return int(round(speed * 1000))
    #         if 'mb' in value_text or 'mbit' in value_text:
    #             return int(round(speed))
    #         if 'kb' in value_text or 'kbit' in value_text:
    #             return max(int(round(speed / 1000)), 1)
    #         if 'bit' in value_text:
    #             return max(int(round(speed / 1_000_000)), 1)

    #     return None

    # @classmethod
    # def _uptime_to_seconds(cls, uptime: Any) -> int:
    #     if not uptime:
    #         return 0

    #     unit_seconds = {
    #         'year': 365 * 24 * 60 * 60,
    #         'week': 7 * 24 * 60 * 60,
    #         'day': 24 * 60 * 60,
    #         'hour': 60 * 60,
    #         'minute': 60,
    #         'second': 1,
    #     }
    #     total = 0
    #     for amount, unit in re.findall(r'(\d+)\s*([A-Za-z]+)', str(uptime)):
    #         for unit_name, multiplier in unit_seconds.items():
    #             if unit.lower().startswith(unit_name):
    #                 total += int(amount) * multiplier
    #                 break
    #     return total
