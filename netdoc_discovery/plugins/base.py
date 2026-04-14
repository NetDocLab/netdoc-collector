"""
Base class for all vendor/platform plugins.

Every plugin must implement:
  - commands()   -> list of CLI commands to run on the device
  - parse()      -> transform raw command outputs into a structured dict
  - to_yaml_dict() -> return the final dict to be serialized into YAML output
"""

from abc import ABC, abstractmethod
import re
import json
from typing import Any
from pathlib import Path
from textfsm.parser import TextFSMError
from nornir.core.task import Task
from nornir_netmiko.tasks import netmiko_send_command
from netmiko.utilities import get_structured_data


class BasePlugin(ABC):
    def __init__(self, host_name: str, host_data: dict, report_path: Path | None):
        """
        Args:
            host_name: Nornir host name (used as key in output)
            host_data: dict of host.data fields from inventory (vendor, site, etc.)
        """
        self.report_path = None
        self.host_name: str = host_name
        self.host_data: dict = host_data

        if report_path:
            # Save report path to save logs locally
            self.report_path = report_path / Path(host_name)
            self.report_path.mkdir(exist_ok=True, parents=True)

    @abstractmethod
    def collect(self, task: Task) -> dict[str, str]:
        """Collect data from devices and return result in NetDoc format."""
        ...

    @abstractmethod
    def to_netdoc_dict(self, parsed_outputs: dict[str, Any]) -> dict[str, Any]:
        """
        Build the finalNetDoc dict for this host.

        Args:
            parsed: output of parse()

        Returns:
            Dict that will be written under this host's key in the output YAML.
        """
        ...

    @staticmethod
    def slugify(text: str):
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        text = re.sub(r'^-+|-+$', '', text)
        return text

    @staticmethod
    def parse_netmiko_output(raw_output, platform, cmd) -> None | list:
        try:
            parsed_output: list = get_structured_data(
                raw_output, platform=platform, command=cmd
            )
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
            with open(
                self.report_path / Path(f'{log_file}.json'), 'w', encoding='utf-8'
            ) as fh:
                json.dump(content, fh, indent=2)
            return

        # Write a RAW content
        with open(self.report_path / Path(f'{log_file}.raw'), 'w') as fh:
            fh.write(content)

    def run_netmiko_cmd(self, task, platform, cmd) -> tuple[str, None | list]:
        parsed_output = None
        cmd_result: str = task.run(
            task=netmiko_send_command,
            command_string=cmd,
            use_textfsm=False,
        )
        raw_output = cmd_result.result
        parsed_output = self.parse_netmiko_output(raw_output, platform, cmd)

        # Dump output files
        self.write_output(raw_output, cmd)
        self.write_output(parsed_output, cmd)

        return raw_output, parsed_output
