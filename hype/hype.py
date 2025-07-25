import logging
import os.path
import time

import schedule
from mastodon import Mastodon

from .config import Config


class Hype:
    def __init__(self, config: Config) -> None:
        self.config = config
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(message)s",
            level=logging.getLevelName(self.config.log_level),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.log = logging.getLogger("hype")
        self.log.info("Config loaded")

    def login(self):
        self.client = self.init_client(self.config.bot_account.server)
        self.log.info(f"Loading access token for {self.config.bot_account.server}")
        self.client.access_token = self.config.bot_account.password

    def update_profile(self):
        self.log.info("Update bot profile")
        subscribed_instances_list = "\n".join(
            [f"- {instance}" for instance in self.config.subscribed_instances]
        )
        note = f"""{self.config.profile_prefix}
        {subscribed_instances_list}
        """
        fields = [(key, value) for key, value in self.config.fields.items()]
        self.client.account_update_credentials(
            note=note, bot=True, discoverable=True, fields=fields
        )

    def boost(self):
        self.log.info("Run boost")
        for instance in self.config.subscribed_instances:
            try:
                # Create mastodon API client
                mastodon_client = self.init_client(instance.name)
                # Fetch statuses from every subscribed instance
                trending_statuses = mastodon_client.trending_statuses()[
                    : instance.limit
                ]
                counter = 0
                for trending_status in trending_statuses:
                    counter += 1
                    # Get snowflake-id of status on the instance where the status will be boosted  # noqa: E501
                    status = self.client.search_v2(
                        trending_status["uri"], result_type="statuses"
                    )["statuses"]
                    if len(status) > 0:
                        status = status[0]
                        # check if post comes from a filtered instance
                        source_account = status["account"]["acct"].split("@")
                        server = source_account[-1]
                        filtered = server in self.config.filtered_instances
                        # Boost if not already boosted
                        already_boosted = status["reblogged"]
                        if not already_boosted and not filtered:
                            self.client.status_reblog(status)
                        self.log.info(
                            f"{instance.name}: {counter}/{len(trending_statuses)} {'ignore' if (already_boosted or filtered)  else 'boost'}"
                        )
                    else:
                        self.log.warning(
                            f"{instance.name}: {counter}/{len(trending_statuses)} could not find post by id"
                        )
            except Exception as e:
                self.log.error(
                    f"{instance.name}: Could not fetch instance. Sorry. - {e}"
                )

    def start(self):
        self.boost()
        self.log.info(f"Schedule run every {self.config.interval} minutes")
        schedule.every(self.config.interval).minutes.do(self.boost)
        while True:
            schedule.run_pending()
            time.sleep(1)

    def init_client(self, instance_name: str) -> Mastodon:
        secrets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "secrets")
        os.makedirs(secrets_dir, exist_ok=True)  # ensure it's created

        secret_path = os.path.join(secrets_dir, f"{instance_name}_clientcred.secret")
        if not os.path.isfile(secret_path):
            self.log.info(f"Initialize client for {instance_name}")
            Mastodon.create_app(
                instance_name,
                api_base_url=f"https://{instance_name}",
                to_file=secret_path,
            )
        else:
            self.log.info(f"Client for {instance_name} is already initialized.")

        return Mastodon(
            client_id=secret_path,
            ratelimit_method="pace",
        )

if __name__ == "__main__":
    config = Config()
    bot = Hype(config)
    bot.login()
    bot.update_profile()
    bot.start()