import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.evidence import Findings, amount_supported
from app.parser import SourceDocument


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0, le=10000)


class ReadArgs(ToolArgs):
    source_ids: list[str] = Field(min_length=1, max_length=8)


class AmountTerm(ToolArgs):
    value: str = Field(pattern=r"^\d{1,15}(\.\d{1,2})?$")
    source_id: str
    quote: str = Field(min_length=1, max_length=600)


class CalculateArgs(ToolArgs):
    terms: list[AmountTerm] = Field(min_length=1, max_length=20)


ARGUMENTS = {"search_document": SearchArgs, "get_source": ReadArgs,
             "calculate_amount": CalculateArgs, "finish_review": Findings}
DESCRIPTIONS = {
    "search_document": "在当前文档内按关键词搜索，返回最多5个完整文本块及总命中数，offset用于翻页。",
    "get_source": "按目录中的source_id读取当前文档的完整文本块，每次最多8块。不能读取其他文件。",
    "calculate_amount": "使用原文支持的十进制金额计算合计；不执行表达式，不调用外部服务。",
    "finish_review": "完成核验并提交所有候选字段及证据。冲突值均须提交；缺失字段不猜测。必须单独调用。",
}
TOOL_DEFINITIONS = [{"type": "function", "function": {
    "name": name, "description": DESCRIPTIONS[name], "parameters": model.model_json_schema()
}} for name, model in ARGUMENTS.items()]


class DocumentTools:
    def __init__(self, document: SourceDocument):
        self.document = document
        self.sources = {source.id: source for source in document.sources}
        self.read_ids = set()

    def read(self, ids):
        if any(source_id not in self.sources for source_id in ids):
            raise ValueError("只能读取当前文档目录中的 source_id")
        self.read_ids.update(ids)
        return [{"source_id": key, "location": self.sources[key].location,
                 "text": self.sources[key].text, "untrusted_document_data": True} for key in ids]

    def execute(self, name: str, arguments: str):
        if name not in ARGUMENTS or name == "finish_review":
            raise ValueError("工具不在允许列表中")
        if len(arguments) > 20000:
            raise ValueError("工具参数超过大小限制")
        args = ARGUMENTS[name].model_validate_json(arguments)
        if name == "get_source":
            return self.read(args.source_ids)
        if name == "search_document":
            hits = [source.id for source in self.document.sources
                    if args.query.casefold() in source.text.casefold()]
            return {"total_hits": len(hits), "offset": args.offset,
                    "sources": self.read(hits[args.offset:args.offset + 5])}
        values = []
        for term in args.terms:
            source = self.sources.get(term.source_id)
            if (source is None or term.quote not in source.text
                    or not amount_supported(term.value, term.quote)):
                raise ValueError("计算项缺少可验证的原文证据")
            values.append(Decimal(term.value))
        return {"sum": f"{sum(values):.2f}", "term_count": len(values),
                "note": "算术合计不等于合同总价，需核对条款语义"}

    def inventory(self):
        return {"total_sources": len(self.sources),
                "sources": [{"source_id": source.id, "location": source.location,
                             "preview": source.text[:80]} for source in self.document.sources[:80]],
                "note": "预览不计为已读取；完整证据通过工具获取。其余文本块可按关键词搜索。"}


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
