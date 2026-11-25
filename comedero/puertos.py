from typing import Protocol


class PublicadorTagsAutorizados(Protocol):
    def publicarTagsAutorizados(self, comederoId: str, tagsAutorizados: list[str]) -> None: ...
