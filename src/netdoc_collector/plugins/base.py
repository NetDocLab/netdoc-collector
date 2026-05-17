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
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from nornir.core.exceptions import NornirSubTaskError
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
        cmd_timeout: int = 240,
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
        self.cmd_timeout: int = cmd_timeout
        self.claim_token: str | None = claim_token
        self.client = client
        self.job_id: str | None = job_id
        self.idempotency_key: str | None = idempotency_key

        if report_path:
            # Save report path to save logs locally
            self.report_path = report_path / Path(host_name)
            self.report_path.mkdir(exist_ok=True, parents=True)

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

    @staticmethod
    def slugify(text: str):
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        text = re.sub(r'^-+|-+$', '', text)
        return text

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

    def run_netmiko_cmd(self, task: Task, platform, cmd) -> tuple[str, None | list]:
        logger.info(f"Running netmiko command '{cmd}' on {self.host_name}")
        try:
            parsed_output = None
            cmd_result: str = task.run(
                task=netmiko_send_command,
                command_string=cmd,
                use_timing=False,
                read_timeout=self.cmd_timeout,
                use_textfsm=False,
            )
            logger.debug(f"Raw output for command '{cmd}' on {self.host_name}: {cmd_result.result}")
        except NornirSubTaskError as e:
            inner = e.result.exception
            if isinstance(inner, NetmikoAuthenticationException):
                logger.error(f"Authentication failed on {self.host_name}")
            elif isinstance(inner, NetmikoTimeoutException):
                logger.error(f"Timeout on {self.host_name} running '{cmd}'")
            else:
                logger.error(f"Error running command '{cmd}' on {self.host_name}: {inner}")
            raise

        # Dump output files
        try:
            raw_output = cmd_result.result
            parsed_output = self.parse_netmiko_output(raw_output, platform, cmd)
        except Exception as e:
            logger.error(f"Error parsing command '{cmd}' output on {self.host_name}: {e}")

        self.write_output(raw_output, cmd)
        self.write_output(parsed_output, cmd)

        return raw_output, parsed_output

    def upload_raw_outputs(self, raw_outputs):
        if self.client:
            logging.info(f"Uploading collected data")
            self.client.discovery_jobs_raw_outputs_create(data=raw_outputs, claim_token=self.claim_token)

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

        # Write a raw content
        with open(self.report_path / Path(f'{log_file}.raw'), 'w') as fh:
            fh.write(content)
