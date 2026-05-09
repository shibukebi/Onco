from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .constants import DRUG_PREFIX, NON_INDEX_DRUG_TAGS
from .utils import normalize_string, stable_unique


THERAPY_MAP = {
    "化疗": "CHEMO",
    "免疫": "IMMUNE",
    "靶向": "TARGETED",
    "ADC": "ADC",
    "双抗免疫": "BISPECIFIC_IMMUNE",
    "激素": "HORMONE",
    "辅助": "SUPPORTIVE",
    "辅助（改善贫血）": "SUPPORTIVE",
    "Solution/Solvent": "SOLVENT",
}


def normalize_dili_level(value: object) -> str | None:
    text = normalize_string(value)
    if not text:
        return None
    text = text.replace("Concern", "concern")
    text = text.replace("DILI风险标注:", "")
    return f"DILI_RISK:{text.upper()}"


@dataclass(slots=True)
class DrugKnowledgeBase:
    by_ingredient: dict[str, dict[str, object]]
    by_trade_name: dict[str, dict[str, object]]

    @classmethod
    def load(cls, resource_dir: str | Path) -> "DrugKnowledgeBase":
        base = Path(resource_dir)
        annotated = pd.read_excel(base / "annotated_unique_drugs.xlsx")
        dili_dict = pd.read_excel(base / "DILI_Risk_Dictionary_Final.xlsx")
        therapy_dict = pd.read_csv(base / "chemo_classification_dictionary 2.csv")

        annotated.columns = [normalize_string(col) for col in annotated.columns]
        dili_dict.columns = [normalize_string(col) for col in dili_dict.columns]
        therapy_dict.columns = [normalize_string(col) for col in therapy_dict.columns]

        dili_map = {
            normalize_string(row["成分名"]).lower(): normalize_dili_level(row["DILI风险标注"])
            for _, row in dili_dict.iterrows()
            if normalize_string(row.get("成分名"))
        }
        therapy_map = {
            normalize_string(row["Standard_Name (成分名)"]).lower(): THERAPY_MAP.get(
                normalize_string(row["Category (药物种类)"]), None
            )
            for _, row in therapy_dict.iterrows()
            if normalize_string(row.get("Standard_Name (成分名)"))
        }
        alias_map = {
            normalize_string(row["Alias (别名/商品名/简写)"]).lower(): THERAPY_MAP.get(
                normalize_string(row["Category (药物种类)"]), None
            )
            for _, row in therapy_dict.iterrows()
            if normalize_string(row.get("Alias (别名/商品名/简写)"))
        }

        by_ingredient: dict[str, dict[str, object]] = {}
        by_trade_name: dict[str, dict[str, object]] = {}
        for _, row in annotated.iterrows():
            ingredient = normalize_string(row.get("药物成分名"))
            trade_name = normalize_string(row.get("药物商品名"))
            atc4 = normalize_string(row.get("药物化学分类(ATC分类4级)"))
            dili_label = normalize_dili_level(row.get("DILI风险标注"))
            therapy = THERAPY_MAP.get(normalize_string(row.get("药物种类")))

            tags = stable_unique(
                [
                    dili_label,
                    therapy,
                    dili_map.get(ingredient.lower()),
                    therapy_map.get(ingredient.lower()),
                    alias_map.get(trade_name.lower()),
                ]
            )

            payload = {
                "ingredient": ingredient,
                "trade_name": trade_name,
                "atc4": atc4,
                "tags": tags,
            }
            if ingredient:
                by_ingredient[ingredient.lower()] = payload
            if trade_name:
                by_trade_name[trade_name.lower()] = payload
        return cls(by_ingredient=by_ingredient, by_trade_name=by_trade_name)

    def annotate(
        self,
        ingredient: object,
        trade_name: object,
        atc2: object,
    ) -> tuple[str, list[str]]:
        ingredient_text = normalize_string(ingredient)
        trade_name_text = normalize_string(trade_name)
        atc2_text = normalize_string(atc2)

        source = None
        if ingredient_text:
            source = self.by_ingredient.get(ingredient_text.lower())
        if source is None and trade_name_text:
            source = self.by_trade_name.get(trade_name_text.lower())

        tags: list[str] = []
        canonical = ingredient_text or trade_name_text
        if source:
            canonical = normalize_string(source.get("ingredient")) or canonical
            tags.extend(source.get("tags", []))

        if "肝胆" in atc2_text or "胆汁" in atc2_text:
            tags.append("HEPATOBILIARY")

        tags = stable_unique(tags)
        concept = f"{DRUG_PREFIX}{canonical}" if canonical else f"{DRUG_PREFIX}UNKNOWN"
        if tags:
            concept = f"{concept}:[{'|'.join(tags)}]"
        return concept, tags

    def annotate_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        work["ingredient_key"] = work.get("药物成分名", "").map(lambda v: normalize_string(v).lower())
        work["trade_key"] = work.get("药物商品名", "").map(lambda v: normalize_string(v).lower())

        ingredient_df = pd.DataFrame.from_dict(self.by_ingredient, orient="index").reset_index().rename(columns={"index": "ingredient_key"})
        trade_df = pd.DataFrame.from_dict(self.by_trade_name, orient="index").reset_index().rename(columns={"index": "trade_key"})

        work = work.merge(
            ingredient_df[["ingredient_key", "ingredient", "trade_name", "tags"]],
            on="ingredient_key",
            how="left",
        )
        work = work.merge(
            trade_df[["trade_key", "ingredient", "trade_name", "tags"]].rename(
                columns={"ingredient": "ingredient_from_trade", "trade_name": "trade_name_from_trade", "tags": "tags_from_trade"}
            ),
            on="trade_key",
            how="left",
        )

        canonical = work["ingredient"].fillna("").replace("", pd.NA).fillna(work.get("药物成分名", ""))
        canonical = canonical.replace("", pd.NA).fillna(work["ingredient_from_trade"]).replace("", pd.NA).fillna(work.get("药物商品名", ""))
        work["canonical_name"] = canonical.map(normalize_string)

        def merge_tags(row: pd.Series) -> list[str]:
            tags = []
            for key in ["tags", "tags_from_trade"]:
                value = row.get(key)
                if isinstance(value, list):
                    tags.extend(value)
            atc2_text = normalize_string(row.get("药物治疗学分类(ATC分类2级)"))
            if "肝胆" in atc2_text or "胆汁" in atc2_text:
                tags.append("HEPATOBILIARY")
            return stable_unique(tags)

        work["resolved_tags"] = work.apply(merge_tags, axis=1)
        work["drug_tags"] = work["resolved_tags"].map(lambda values: "|".join(values))
        work["source_concept_id"] = work["canonical_name"].map(lambda name: f"{DRUG_PREFIX}{name}" if name else f"{DRUG_PREFIX}UNKNOWN")
        mask = work["resolved_tags"].map(bool)
        work.loc[mask, "source_concept_id"] = work.loc[mask].apply(
            lambda row: f"{DRUG_PREFIX}{row['canonical_name']}:[{'|'.join(row['resolved_tags'])}]",
            axis=1,
        )
        return work


def is_index_therapy(tags: list[str]) -> bool:
    tag_set = set(tags)
    return bool(tag_set - NON_INDEX_DRUG_TAGS) and any(
        tag in tag_set for tag in {"CHEMO", "IMMUNE", "TARGETED", "ADC", "BISPECIFIC_IMMUNE"}
    )
