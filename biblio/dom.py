"""DOM mínimo sobre el parser de la librería estándar.

El OPAC no necesita un parser completo: solo queremos encontrar elementos por
atributo y leer texto. `html.parser` de la stdlib cubre el caso y evita añadir
dependencias, que es justo lo que queremos para que el motor sea portable tal
cual a Kotlin.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Callable, Iterator

VOID_TAGS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None"):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []
        self.parent = parent

    # -- recorrido -------------------------------------------------------
    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def find_all(
        self,
        tag: str | None = None,
        predicate: Callable[["Node"], bool] | None = None,
    ) -> list["Node"]:
        found = []
        for node in self.walk():
            if self is node:
                continue
            if tag is not None and node.tag != tag:
                continue
            if predicate is not None and not predicate(node):
                continue
            found.append(node)
        return found

    def find(
        self,
        tag: str | None = None,
        predicate: Callable[["Node"], bool] | None = None,
    ) -> "Node | None":
        found = self.find_all(tag, predicate)
        return found[0] if found else None

    def by_id(self, element_id: str) -> "Node | None":
        return self.find(predicate=lambda n: n.attrs.get("id") == element_id)

    def by_class(self, class_name: str) -> list["Node"]:
        return self.find_all(
            predicate=lambda n: class_name in n.attrs.get("class", "").split()
        )

    def first_by_class(self, class_name: str) -> "Node | None":
        found = self.by_class(class_name)
        return found[0] if found else None

    # -- lectura ---------------------------------------------------------
    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def has_class(self, class_name: str) -> bool:
        return class_name in self.attrs.get("class", "").split()

    def text(self, separator: str = " ") -> str:
        parts: list[str] = []

        def collect(node: Node) -> None:
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                else:
                    collect(child)

        collect(self)
        return re.sub(r"\s+", " ", separator.join(parts)).strip()

    def own_text(self) -> str:
        return re.sub(
            r"\s+", " ", " ".join(c for c in self.children if isinstance(c, str))
        ).strip()

    def outer_html(self) -> str:
        from html import escape

        attrs = "".join(
            f' {k}="{escape(v, quote=True)}"' for k, v in self.attrs.items()
        )
        inner = "".join(
            child if isinstance(child, str) else child.outer_html()
            for child in self.children
        )
        if self.tag in VOID_TAGS:
            return f"<{self.tag}{attrs}>"
        return f"<{self.tag}{attrs}>{inner}</{self.tag}>"

    def __repr__(self) -> str:
        return f"<Node {self.tag} {self.attrs.get('id') or self.attrs.get('class') or ''}>"


class Root(Node):
    def __init__(self) -> None:
        super().__init__("#document", {}, None)


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Root()
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].children.append(data)


def parse(html: str) -> Root:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root