class InstanceNotFoundException(Exception):
    def __init__(self, instance_type: str, instance_id: int) -> None:
        super().__init__(f"{instance_type} with id {instance_id} was not found in the server")
