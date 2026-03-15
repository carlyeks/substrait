#!/usr/bin/env python3
"""
Generate Substrait logical plan JSON example files.

This script generates 50+ example Substrait plan files covering TPC-H schemas
and various SQL patterns.
"""

import json
import os
import sys
import traceback

from substrait.builders import plan as p
from substrait.builders import extended_expression as ee
from substrait import type_pb2 as stt, algebra_pb2 as stalg
from substrait.extension_registry import ExtensionRegistry
from google.protobuf import json_format

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Type constants
# ---------------------------------------------------------------------------
INT32_REQ = stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED))
INT64_REQ = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED))
FP64_REQ  = stt.Type(fp64=stt.Type.FP64(nullability=stt.Type.NULLABILITY_REQUIRED))
STR_NULL  = stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE))
STR_REQ   = stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_REQUIRED))
DATE_REQ  = stt.Type(date=stt.Type.Date(nullability=stt.Type.NULLABILITY_REQUIRED))
DATE_NULL = stt.Type(date=stt.Type.Date(nullability=stt.Type.NULLABILITY_NULLABLE))
DEC_NULL  = stt.Type(decimal=stt.Type.Decimal(precision=15, scale=2, nullability=stt.Type.NULLABILITY_NULLABLE))
DEC_REQ   = stt.Type(decimal=stt.Type.Decimal(precision=15, scale=2, nullability=stt.Type.NULLABILITY_REQUIRED))
BOOL_REQ  = stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED))

# ---------------------------------------------------------------------------
# Function URNs
# ---------------------------------------------------------------------------
ARITH = "extension:io.substrait:functions_arithmetic"
CMP   = "extension:io.substrait:functions_comparison"
BOOL  = "extension:io.substrait:functions_boolean"
STR_F = "extension:io.substrait:functions_string"
AGG   = "extension:io.substrait:functions_aggregate_generic"
ROUND = "extension:io.substrait:functions_rounding"
LOGF  = "extension:io.substrait:functions_logarithmic"
DT    = "extension:io.substrait:functions_datetime"

# ---------------------------------------------------------------------------
# TPC-H schemas
# ---------------------------------------------------------------------------
def named_struct(names, types):
    return stt.NamedStruct(
        names=names,
        struct=stt.Type.Struct(types=types, nullability=stt.Type.NULLABILITY_REQUIRED)
    )

LINEITEM_SCHEMA = named_struct(
    ["l_orderkey", "l_partkey", "l_suppkey", "l_linenumber",
     "l_quantity", "l_extendedprice", "l_discount", "l_tax",
     "l_returnflag", "l_linestatus", "l_shipdate", "l_commitdate",
     "l_receiptdate", "l_shipinstruct", "l_shipmode", "l_comment"],
    [INT64_REQ, INT64_REQ, INT64_REQ, INT32_REQ,
     FP64_REQ, FP64_REQ, FP64_REQ, FP64_REQ,
     STR_REQ, STR_REQ, DATE_REQ, DATE_REQ,
     DATE_REQ, STR_NULL, STR_NULL, STR_NULL]
)

ORDERS_SCHEMA = named_struct(
    ["o_orderkey", "o_custkey", "o_orderstatus", "o_totalprice",
     "o_orderdate", "o_orderpriority", "o_clerk", "o_shippriority", "o_comment"],
    [INT64_REQ, INT64_REQ, STR_REQ, FP64_REQ,
     DATE_REQ, STR_NULL, STR_NULL, INT32_REQ, STR_NULL]
)

CUSTOMER_SCHEMA = named_struct(
    ["c_custkey", "c_name", "c_address", "c_nationkey",
     "c_phone", "c_acctbal", "c_mktsegment", "c_comment"],
    [INT64_REQ, STR_REQ, STR_NULL, INT64_REQ,
     STR_NULL, FP64_REQ, STR_NULL, STR_NULL]
)

PART_SCHEMA = named_struct(
    ["p_partkey", "p_name", "p_mfgr", "p_brand",
     "p_type", "p_size", "p_container", "p_retailprice", "p_comment"],
    [INT64_REQ, STR_REQ, STR_NULL, STR_NULL,
     STR_NULL, INT32_REQ, STR_NULL, FP64_REQ, STR_NULL]
)

SUPPLIER_SCHEMA = named_struct(
    ["s_suppkey", "s_name", "s_address", "s_nationkey",
     "s_phone", "s_acctbal", "s_comment"],
    [INT64_REQ, STR_REQ, STR_NULL, INT64_REQ,
     STR_NULL, FP64_REQ, STR_NULL]
)

PARTSUPP_SCHEMA = named_struct(
    ["ps_partkey", "ps_suppkey", "ps_availqty", "ps_supplycost", "ps_comment"],
    [INT64_REQ, INT64_REQ, INT32_REQ, FP64_REQ, STR_NULL]
)

NATION_SCHEMA = named_struct(
    ["n_nationkey", "n_name", "n_regionkey", "n_comment"],
    [INT64_REQ, STR_REQ, INT64_REQ, STR_NULL]
)

REGION_SCHEMA = named_struct(
    ["r_regionkey", "r_name", "r_comment"],
    [INT64_REQ, STR_REQ, STR_NULL]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
registry = ExtensionRegistry()

def sort_field(col_idx, direction=stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST):
    """Return a (column_expr, direction) tuple for p.sort()."""
    return (ee.column(col_idx), direction)

def save(filename, plan_fn, sql_query=""):
    """Resolve, enrich with sql_query, and save a plan to a JSON file."""
    bound = plan_fn(registry)
    data = json.loads(json_format.MessageToJson(bound))
    if sql_query:
        data["sql_query"] = sql_query
    out_path = os.path.join(OUTPUT_DIR, filename)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    return out_path

generated = []
failed = []

def gen(name, fn, sql=""):
    try:
        path = fn()
        generated.append(name)
        print(f"  OK  {name}")
    except Exception as e:
        failed.append((name, str(e)))
        print(f"  ERR {name}: {e}")


# ===========================================================================
# 1. Simple table scans
# ===========================================================================
def ex_lineitem_scan():
    return save("lineitem_scan.json",
        p.read_named_table("lineitem", LINEITEM_SCHEMA),
        "SELECT * FROM lineitem")

def ex_orders_scan():
    return save("orders_scan.json",
        p.read_named_table("orders", ORDERS_SCHEMA),
        "SELECT * FROM orders")

def ex_customer_scan():
    return save("customer_scan.json",
        p.read_named_table("customer", CUSTOMER_SCHEMA),
        "SELECT * FROM customer")

def ex_part_scan():
    return save("part_scan.json",
        p.read_named_table("part", PART_SCHEMA),
        "SELECT * FROM part")

def ex_supplier_scan():
    return save("supplier_scan.json",
        p.read_named_table("supplier", SUPPLIER_SCHEMA),
        "SELECT * FROM supplier")

def ex_nation_scan():
    return save("nation_scan.json",
        p.read_named_table("nation", NATION_SCHEMA),
        "SELECT * FROM nation")

def ex_region_scan():
    return save("region_scan.json",
        p.read_named_table("region", REGION_SCHEMA),
        "SELECT * FROM region")

# ===========================================================================
# 2. Column projections (SELECT)
# ===========================================================================
def ex_lineitem_select_key_qty():
    return save("lineitem_select_key_qty.json",
        p.select(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [ee.column("l_orderkey"), ee.column("l_quantity"), ee.column("l_extendedprice")]
        ),
        "SELECT l_orderkey, l_quantity, l_extendedprice FROM lineitem")

def ex_customer_select_name_seg():
    return save("customer_select_name_seg.json",
        p.select(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.column("c_custkey"), ee.column("c_name"), ee.column("c_mktsegment")]
        ),
        "SELECT c_custkey, c_name, c_mktsegment FROM customer")

def ex_orders_select_key_date():
    return save("orders_select_key_date.json",
        p.select(
            p.read_named_table("orders", ORDERS_SCHEMA),
            [ee.column("o_orderkey"), ee.column("o_orderdate"), ee.column("o_totalprice")]
        ),
        "SELECT o_orderkey, o_orderdate, o_totalprice FROM orders")

# ===========================================================================
# 3. Filters
# ===========================================================================
def ex_filter_quantity_gt():
    return save("filter_quantity_gt.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(30.0, FP64_REQ)])
        ),
        "SELECT * FROM lineitem WHERE l_quantity > 30")

def ex_filter_discount_lt():
    return save("filter_discount_lt.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(CMP, "lt", [ee.column("l_discount"), ee.literal(0.05, FP64_REQ)])
        ),
        "SELECT * FROM lineitem WHERE l_discount < 0.05")

def ex_filter_orders_totalprice():
    return save("filter_orders_totalprice.json",
        p.filter(
            p.read_named_table("orders", ORDERS_SCHEMA),
            ee.scalar_function(CMP, "gte", [ee.column("o_totalprice"), ee.literal(10000.0, FP64_REQ)])
        ),
        "SELECT * FROM orders WHERE o_totalprice >= 10000")

def ex_filter_customer_acctbal_positive():
    return save("filter_customer_acctbal_positive.json",
        p.filter(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            ee.scalar_function(CMP, "gt", [ee.column("c_acctbal"), ee.literal(0.0, FP64_REQ)])
        ),
        "SELECT * FROM customer WHERE c_acctbal > 0")

def ex_filter_is_null():
    return save("filter_comment_is_null.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(CMP, "is_null", [ee.column("l_comment")])
        ),
        "SELECT * FROM lineitem WHERE l_comment IS NULL")

def ex_filter_is_not_null():
    return save("filter_comment_is_not_null.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(CMP, "is_not_null", [ee.column("l_comment")])
        ),
        "SELECT * FROM lineitem WHERE l_comment IS NOT NULL")

def ex_filter_and_compound():
    return save("filter_and_compound.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(BOOL, "and", [
                ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(10.0, FP64_REQ)]),
                ee.scalar_function(CMP, "lt", [ee.column("l_discount"), ee.literal(0.08, FP64_REQ)])
            ])
        ),
        "SELECT * FROM lineitem WHERE l_quantity > 10 AND l_discount < 0.08")

def ex_filter_or_compound():
    return save("filter_or_compound.json",
        p.filter(
            p.read_named_table("orders", ORDERS_SCHEMA),
            ee.scalar_function(BOOL, "or", [
                ee.scalar_function(CMP, "equal", [ee.column("o_orderstatus"), ee.literal("O", STR_REQ)]),
                ee.scalar_function(CMP, "equal", [ee.column("o_orderstatus"), ee.literal("P", STR_REQ)])
            ])
        ),
        "SELECT * FROM orders WHERE o_orderstatus = 'O' OR o_orderstatus = 'P'")

def ex_filter_not():
    return save("filter_not.json",
        p.filter(
            p.read_named_table("orders", ORDERS_SCHEMA),
            ee.scalar_function(BOOL, "not", [
                ee.scalar_function(CMP, "equal", [ee.column("o_orderstatus"), ee.literal("F", STR_REQ)])
            ])
        ),
        "SELECT * FROM orders WHERE NOT o_orderstatus = 'F'")

def ex_filter_between():
    return save("filter_quantity_between.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(CMP, "between", [
                ee.column("l_quantity"),
                ee.literal(10.0, FP64_REQ),
                ee.literal(50.0, FP64_REQ)
            ])
        ),
        "SELECT * FROM lineitem WHERE l_quantity BETWEEN 10 AND 50")

def ex_filter_like():
    return save("filter_name_like.json",
        p.filter(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            ee.scalar_function(STR_F, "like", [ee.column("c_name"), ee.literal("Customer%", STR_REQ)])
        ),
        "SELECT * FROM customer WHERE c_name LIKE 'Customer%'")

def ex_filter_starts_with():
    return save("filter_name_starts_with.json",
        p.filter(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            ee.scalar_function(STR_F, "starts_with", [ee.column("c_name"), ee.literal("Cust", STR_REQ)])
        ),
        "SELECT * FROM customer WHERE c_name LIKE 'Cust%'")

def ex_filter_three_conditions():
    return save("filter_three_conditions.json",
        p.filter(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            ee.scalar_function(BOOL, "and", [
                ee.scalar_function(BOOL, "and", [
                    ee.scalar_function(CMP, "gte", [ee.column("l_discount"), ee.literal(0.05, FP64_REQ)]),
                    ee.scalar_function(CMP, "lte", [ee.column("l_discount"), ee.literal(0.07, FP64_REQ)])
                ]),
                ee.scalar_function(CMP, "lt", [ee.column("l_quantity"), ee.literal(24.0, FP64_REQ)])
            ])
        ),
        "SELECT * FROM lineitem WHERE l_discount >= 0.05 AND l_discount <= 0.07 AND l_quantity < 24")

# ===========================================================================
# 4. Aggregations
# ===========================================================================
def ex_agg_count_all():
    return save("agg_count_all.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("l_orderkey")])
            ]
        ),
        "SELECT COUNT(l_orderkey) FROM lineitem")

def ex_agg_sum_qty():
    return save("agg_sum_qty.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[],
            measures=[
                ee.aggregate_function(ARITH, "sum", [ee.column("l_quantity")])
            ]
        ),
        "SELECT SUM(l_quantity) FROM lineitem")

def ex_agg_avg_discount():
    return save("agg_avg_discount.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[],
            measures=[
                ee.aggregate_function(ARITH, "avg", [ee.column("l_discount")])
            ]
        ),
        "SELECT AVG(l_discount) FROM lineitem")

def ex_agg_min_max_price():
    return save("agg_min_max_price.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[],
            measures=[
                ee.aggregate_function(ARITH, "min", [ee.column("l_extendedprice")]),
                ee.aggregate_function(ARITH, "max", [ee.column("l_extendedprice")])
            ]
        ),
        "SELECT MIN(l_extendedprice), MAX(l_extendedprice) FROM lineitem")

def ex_agg_group_by_returnflag():
    return save("agg_group_by_returnflag.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[ee.column("l_returnflag"), ee.column("l_linestatus")],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("l_orderkey")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("l_quantity")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("l_extendedprice")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("l_quantity")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("l_extendedprice")])
            ]
        ),
        "SELECT l_returnflag, l_linestatus, COUNT(*), SUM(l_quantity), SUM(l_extendedprice), AVG(l_quantity), AVG(l_extendedprice) FROM lineitem GROUP BY l_returnflag, l_linestatus")

def ex_agg_group_by_orderstatus():
    return save("agg_group_by_orderstatus.json",
        p.aggregate(
            p.read_named_table("orders", ORDERS_SCHEMA),
            grouping_expressions=[ee.column("o_orderstatus")],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("o_orderkey")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("o_totalprice")])
            ]
        ),
        "SELECT o_orderstatus, COUNT(*), SUM(o_totalprice) FROM orders GROUP BY o_orderstatus")

def ex_agg_group_by_mktsegment():
    return save("agg_group_by_mktsegment.json",
        p.aggregate(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            grouping_expressions=[ee.column("c_mktsegment")],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("c_custkey")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("c_acctbal")])
            ]
        ),
        "SELECT c_mktsegment, COUNT(*), AVG(c_acctbal) FROM customer GROUP BY c_mktsegment")

def ex_agg_group_by_nationkey():
    return save("agg_group_by_nationkey.json",
        p.aggregate(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            grouping_expressions=[ee.column("c_nationkey")],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("c_custkey")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("c_acctbal")])
            ]
        ),
        "SELECT c_nationkey, COUNT(*), SUM(c_acctbal) FROM customer GROUP BY c_nationkey")

# ===========================================================================
# 5. Joins
# ===========================================================================
def ex_join_orders_customer_inner():
    return save("join_orders_customer_inner.json",
        p.join(
            p.read_named_table("orders", ORDERS_SCHEMA),
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(1),  # o_custkey
                ee.column(len(ORDERS_SCHEMA.names) + 0)  # c_custkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM orders INNER JOIN customer ON o_custkey = c_custkey")

def ex_join_lineitem_orders_inner():
    return save("join_lineitem_orders_inner.json",
        p.join(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            p.read_named_table("orders", ORDERS_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(0),  # l_orderkey
                ee.column(len(LINEITEM_SCHEMA.names) + 0)  # o_orderkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM lineitem INNER JOIN orders ON l_orderkey = o_orderkey")

def ex_join_orders_customer_left():
    return save("join_orders_customer_left.json",
        p.join(
            p.read_named_table("orders", ORDERS_SCHEMA),
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(1),  # o_custkey
                ee.column(len(ORDERS_SCHEMA.names) + 0)  # c_custkey
            ]),
            stalg.JoinRel.JOIN_TYPE_LEFT
        ),
        "SELECT * FROM orders LEFT JOIN customer ON o_custkey = c_custkey")

def ex_join_nation_region():
    return save("join_nation_region.json",
        p.join(
            p.read_named_table("nation", NATION_SCHEMA),
            p.read_named_table("region", REGION_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(2),  # n_regionkey
                ee.column(len(NATION_SCHEMA.names) + 0)  # r_regionkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM nation INNER JOIN region ON n_regionkey = r_regionkey")

def ex_join_supplier_nation():
    return save("join_supplier_nation.json",
        p.join(
            p.read_named_table("supplier", SUPPLIER_SCHEMA),
            p.read_named_table("nation", NATION_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(3),  # s_nationkey
                ee.column(len(SUPPLIER_SCHEMA.names) + 0)  # n_nationkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM supplier INNER JOIN nation ON s_nationkey = n_nationkey")

def ex_join_partsupp_part():
    return save("join_partsupp_part.json",
        p.join(
            p.read_named_table("partsupp", PARTSUPP_SCHEMA),
            p.read_named_table("part", PART_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(0),  # ps_partkey
                ee.column(len(PARTSUPP_SCHEMA.names) + 0)  # p_partkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM partsupp INNER JOIN part ON ps_partkey = p_partkey")

# ===========================================================================
# 6. ORDER BY (sort)
# ===========================================================================
def ex_sort_lineitem_qty_asc():
    return save("sort_lineitem_qty_asc.json",
        p.sort(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [sort_field(4, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST)]  # l_quantity
        ),
        "SELECT * FROM lineitem ORDER BY l_quantity ASC")

def ex_sort_orders_totalprice_desc():
    return save("sort_orders_totalprice_desc.json",
        p.sort(
            p.read_named_table("orders", ORDERS_SCHEMA),
            [sort_field(3, stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST)]  # o_totalprice
        ),
        "SELECT * FROM orders ORDER BY o_totalprice DESC")

def ex_sort_customer_acctbal_desc():
    return save("sort_customer_acctbal_desc.json",
        p.sort(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [sort_field(5, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]  # c_acctbal
        ),
        "SELECT * FROM customer ORDER BY c_acctbal DESC")

def ex_sort_multi_column():
    return save("sort_multi_column.json",
        p.sort(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [
                sort_field(8, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST),   # l_returnflag
                sort_field(9, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST),   # l_linestatus
            ]
        ),
        "SELECT * FROM lineitem ORDER BY l_returnflag ASC, l_linestatus ASC")

# ===========================================================================
# 7. LIMIT / OFFSET (fetch)
# ===========================================================================
def ex_fetch_top10():
    return save("fetch_top10.json",
        p.fetch(
            p.read_named_table("orders", ORDERS_SCHEMA),
            offset=None,
            count=ee.literal(10, INT64_REQ)
        ),
        "SELECT * FROM orders LIMIT 10")

def ex_fetch_offset():
    return save("fetch_offset.json",
        p.fetch(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            offset=ee.literal(100, INT64_REQ),
            count=ee.literal(50, INT64_REQ)
        ),
        "SELECT * FROM customer LIMIT 50 OFFSET 100")

# ===========================================================================
# 8. Combinations
# ===========================================================================
def ex_filter_project():
    return save("filter_project.json",
        p.select(
            p.filter(
                p.read_named_table("lineitem", LINEITEM_SCHEMA),
                ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(30.0, FP64_REQ)])
            ),
            [ee.column("l_orderkey"), ee.column("l_quantity"), ee.column("l_extendedprice")]
        ),
        "SELECT l_orderkey, l_quantity, l_extendedprice FROM lineitem WHERE l_quantity > 30")

def ex_filter_agg():
    return save("filter_agg.json",
        p.aggregate(
            p.filter(
                p.read_named_table("lineitem", LINEITEM_SCHEMA),
                ee.scalar_function(CMP, "lte", [ee.column("l_discount"), ee.literal(0.07, FP64_REQ)])
            ),
            grouping_expressions=[ee.column("l_returnflag")],
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column("l_orderkey")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("l_extendedprice")])
            ]
        ),
        "SELECT l_returnflag, COUNT(*), SUM(l_extendedprice) FROM lineitem WHERE l_discount <= 0.07 GROUP BY l_returnflag")

def ex_agg_sort():
    return save("agg_sort.json",
        p.sort(
            p.aggregate(
                p.read_named_table("orders", ORDERS_SCHEMA),
                grouping_expressions=[ee.column("o_orderstatus")],
                measures=[
                    ee.aggregate_function(AGG, "count", [ee.column("o_orderkey")])
                ]
            ),
            [sort_field(0, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST)]
        ),
        "SELECT o_orderstatus, COUNT(*) FROM orders GROUP BY o_orderstatus ORDER BY o_orderstatus")

def ex_filter_agg_sort_limit():
    return save("filter_agg_sort_limit.json",
        p.fetch(
            p.sort(
                p.aggregate(
                    p.filter(
                        p.read_named_table("lineitem", LINEITEM_SCHEMA),
                        ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(5.0, FP64_REQ)])
                    ),
                    grouping_expressions=[ee.column("l_returnflag")],
                    measures=[
                        ee.aggregate_function(ARITH, "sum", [ee.column("l_extendedprice")])
                    ]
                ),
                [sort_field(1, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]
            ),
            offset=None,
            count=ee.literal(5, INT64_REQ)
        ),
        "SELECT l_returnflag, SUM(l_extendedprice) FROM lineitem WHERE l_quantity > 5 GROUP BY l_returnflag ORDER BY SUM(l_extendedprice) DESC LIMIT 5")

def ex_join_filter_select():
    return save("join_filter_select.json",
        p.select(
            p.filter(
                p.join(
                    p.read_named_table("orders", ORDERS_SCHEMA),
                    p.read_named_table("customer", CUSTOMER_SCHEMA),
                    ee.scalar_function(CMP, "equal", [
                        ee.column(1),
                        ee.column(len(ORDERS_SCHEMA.names) + 0)
                    ]),
                    stalg.JoinRel.JOIN_TYPE_INNER
                ),
                ee.scalar_function(CMP, "gte", [ee.column(3), ee.literal(5000.0, FP64_REQ)])  # o_totalprice
            ),
            [ee.column(0), ee.column(3), ee.column(len(ORDERS_SCHEMA.names) + 1)]  # o_orderkey, o_totalprice, c_name
        ),
        "SELECT o_orderkey, o_totalprice, c_name FROM orders INNER JOIN customer ON o_custkey = c_custkey WHERE o_totalprice >= 5000")

def ex_sort_fetch_combined():
    return save("sort_fetch_combined.json",
        p.fetch(
            p.sort(
                p.read_named_table("customer", CUSTOMER_SCHEMA),
                [sort_field(5, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]  # c_acctbal
            ),
            offset=None,
            count=ee.literal(100, INT64_REQ)
        ),
        "SELECT * FROM customer ORDER BY c_acctbal DESC LIMIT 100")

# ===========================================================================
# 9. String operations
# ===========================================================================
def ex_string_upper():
    return save("string_upper.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(STR_F, "upper", [ee.column("c_name")])]
        ),
        "SELECT UPPER(c_name) FROM customer")

def ex_string_lower():
    return save("string_lower.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(STR_F, "lower", [ee.column("c_name")])]
        ),
        "SELECT LOWER(c_name) FROM customer")

def ex_string_length():
    return save("string_length.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(STR_F, "char_length", [ee.column("c_name")])]
        ),
        "SELECT CHAR_LENGTH(c_name) FROM customer")

def ex_string_concat():
    return save("string_concat.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(STR_F, "concat", [
                ee.column("c_name"), ee.literal(" - ", STR_REQ), ee.column("c_mktsegment")
            ])]
        ),
        "SELECT c_name || ' - ' || c_mktsegment FROM customer")

def ex_string_substring():
    return save("string_substring.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(STR_F, "substring", [
                ee.column("c_name"),
                ee.literal(1, INT32_REQ),
                ee.literal(8, INT32_REQ)
            ])]
        ),
        "SELECT SUBSTRING(c_name, 1, 8) FROM customer")

def ex_string_trim():
    return save("string_trim.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [
                ee.scalar_function(STR_F, "upper", [ee.column("c_name")]),
                ee.scalar_function(STR_F, "lower", [ee.column("c_mktsegment")])
            ]
        ),
        "SELECT UPPER(c_name), LOWER(c_mktsegment) FROM customer")

# ===========================================================================
# 10. Arithmetic / math operations
# ===========================================================================
def ex_arith_multiply():
    return save("arith_multiply.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [ee.scalar_function(ARITH, "multiply", [
                ee.column("l_extendedprice"),
                ee.scalar_function(ARITH, "subtract", [
                    ee.literal(1.0, FP64_REQ),
                    ee.column("l_discount")
                ])
            ])]
        ),
        "SELECT l_extendedprice * (1 - l_discount) FROM lineitem")

def ex_arith_revenue_with_tax():
    return save("arith_revenue_with_tax.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [ee.scalar_function(ARITH, "multiply", [
                ee.scalar_function(ARITH, "multiply", [
                    ee.column("l_extendedprice"),
                    ee.scalar_function(ARITH, "subtract", [
                        ee.literal(1.0, FP64_REQ),
                        ee.column("l_discount")
                    ])
                ]),
                ee.scalar_function(ARITH, "add", [
                    ee.literal(1.0, FP64_REQ),
                    ee.column("l_tax")
                ])
            ])]
        ),
        "SELECT l_extendedprice * (1 - l_discount) * (1 + l_tax) FROM lineitem")

def ex_arith_abs():
    return save("arith_abs.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(ARITH, "abs", [ee.column("c_acctbal")])]
        ),
        "SELECT ABS(c_acctbal) FROM customer")

def ex_arith_negate():
    return save("arith_negate.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [ee.scalar_function(ARITH, "negate", [ee.column("c_acctbal")])]
        ),
        "SELECT -c_acctbal FROM customer")

def ex_round_ceil_floor():
    return save("round_ceil_floor.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [
                ee.scalar_function(ROUND, "ceil", [ee.column("l_discount")]),
                ee.scalar_function(ROUND, "floor", [ee.column("l_discount")])
            ]
        ),
        "SELECT CEIL(l_discount), FLOOR(l_discount) FROM lineitem")

def ex_sqrt_power():
    return save("sqrt_power.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [
                ee.scalar_function(ARITH, "sqrt", [ee.column("l_quantity")]),
                ee.scalar_function(ARITH, "power", [ee.column("l_quantity"), ee.literal(2.0, FP64_REQ)])
            ]
        ),
        "SELECT SQRT(l_quantity), POWER(l_quantity, 2) FROM lineitem")

# ===========================================================================
# 11. TPC-H inspired queries
# ===========================================================================
def ex_tpch_q1_pricing_summary():
    """TPC-H Q1: Pricing Summary Report."""
    return save("tpch_q1_pricing_summary.json",
        p.aggregate(
            p.filter(
                p.read_named_table("lineitem", LINEITEM_SCHEMA),
                ee.scalar_function(CMP, "lte", [
                    ee.column("l_discount"),
                    ee.literal(0.07, FP64_REQ)
                ])
            ),
            grouping_expressions=[ee.column("l_returnflag"), ee.column("l_linestatus")],
            measures=[
                ee.aggregate_function(ARITH, "sum", [ee.column("l_quantity")]),
                ee.aggregate_function(ARITH, "sum", [ee.column("l_extendedprice")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("l_quantity")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("l_extendedprice")]),
                ee.aggregate_function(ARITH, "avg", [ee.column("l_discount")]),
                ee.aggregate_function(AGG, "count", [ee.column("l_orderkey")])
            ]
        ),
        "SELECT l_returnflag, l_linestatus, SUM(l_quantity), SUM(l_extendedprice), AVG(l_quantity), AVG(l_extendedprice), AVG(l_discount), COUNT(*) FROM lineitem WHERE l_discount <= 0.07 GROUP BY l_returnflag, l_linestatus ORDER BY l_returnflag, l_linestatus")

def ex_tpch_q3_shipping():
    """TPC-H Q3: Shipping Priority (simplified)."""
    return save("tpch_q3_shipping.json",
        p.sort(
            p.fetch(
                p.aggregate(
                    p.filter(
                        p.join(
                            p.join(
                                p.filter(
                                    p.read_named_table("customer", CUSTOMER_SCHEMA),
                                    ee.scalar_function(CMP, "equal", [
                                        ee.column("c_mktsegment"),
                                        ee.literal("BUILDING", STR_NULL)
                                    ])
                                ),
                                p.read_named_table("orders", ORDERS_SCHEMA),
                                ee.scalar_function(CMP, "equal", [
                                    ee.column(0),  # c_custkey
                                    ee.column(len(CUSTOMER_SCHEMA.names) + 1)  # o_custkey
                                ]),
                                stalg.JoinRel.JOIN_TYPE_INNER
                            ),
                            p.read_named_table("lineitem", LINEITEM_SCHEMA),
                            ee.scalar_function(CMP, "equal", [
                                ee.column(len(CUSTOMER_SCHEMA.names) + 0),  # o_orderkey
                                ee.column(len(CUSTOMER_SCHEMA.names) + len(ORDERS_SCHEMA.names) + 0)  # l_orderkey
                            ]),
                            stalg.JoinRel.JOIN_TYPE_INNER
                        ),
                        ee.scalar_function(CMP, "is_not_null", [
                            ee.column(len(CUSTOMER_SCHEMA.names) + 0)  # o_orderkey
                        ])
                    ),
                    grouping_expressions=[
                        ee.column(len(CUSTOMER_SCHEMA.names) + 0),  # o_orderkey
                        ee.column(len(CUSTOMER_SCHEMA.names) + 4),  # o_orderdate
                        ee.column(len(CUSTOMER_SCHEMA.names) + 7),  # o_shippriority
                    ],
                    measures=[
                        ee.aggregate_function(ARITH, "sum", [
                            ee.column(len(CUSTOMER_SCHEMA.names) + len(ORDERS_SCHEMA.names) + 5)  # l_extendedprice
                        ])
                    ]
                ),
                offset=None,
                count=ee.literal(10, INT64_REQ)
            ),
            [sort_field(3, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]
        ),
        "SELECT o_orderkey, SUM(l_extendedprice*(1-l_discount)) AS revenue, o_orderdate, o_shippriority FROM customer, orders, lineitem WHERE c_mktsegment = 'BUILDING' AND c_custkey = o_custkey AND l_orderkey = o_orderkey GROUP BY o_orderkey, o_orderdate, o_shippriority ORDER BY revenue DESC LIMIT 10")

def ex_tpch_q5_local_supplier():
    """TPC-H Q5: Local Supplier Volume (simplified)."""
    return save("tpch_q5_local_supplier.json",
        p.aggregate(
            p.join(
                p.join(
                    p.read_named_table("nation", NATION_SCHEMA),
                    p.read_named_table("supplier", SUPPLIER_SCHEMA),
                    ee.scalar_function(CMP, "equal", [
                        ee.column(0),  # n_nationkey
                        ee.column(len(NATION_SCHEMA.names) + 3)  # s_nationkey
                    ]),
                    stalg.JoinRel.JOIN_TYPE_INNER
                ),
                p.read_named_table("region", REGION_SCHEMA),
                ee.scalar_function(CMP, "equal", [
                    ee.column(2),  # n_regionkey
                    ee.column(len(NATION_SCHEMA.names) + len(SUPPLIER_SCHEMA.names) + 0)  # r_regionkey
                ]),
                stalg.JoinRel.JOIN_TYPE_INNER
            ),
            grouping_expressions=[ee.column(1)],  # n_name
            measures=[
                ee.aggregate_function(AGG, "count", [ee.column(0)])
            ]
        ),
        "SELECT n_name, COUNT(*) FROM nation INNER JOIN supplier ON n_nationkey = s_nationkey INNER JOIN region ON n_regionkey = r_regionkey GROUP BY n_name")

def ex_tpch_q6_revenue():
    """TPC-H Q6: Forecasting Revenue Change."""
    return save("tpch_q6_revenue.json",
        p.aggregate(
            p.filter(
                p.read_named_table("lineitem", LINEITEM_SCHEMA),
                ee.scalar_function(BOOL, "and", [
                    ee.scalar_function(BOOL, "and", [
                        ee.scalar_function(CMP, "gte", [ee.column("l_discount"), ee.literal(0.05, FP64_REQ)]),
                        ee.scalar_function(CMP, "lte", [ee.column("l_discount"), ee.literal(0.07, FP64_REQ)])
                    ]),
                    ee.scalar_function(CMP, "lt", [ee.column("l_quantity"), ee.literal(24.0, FP64_REQ)])
                ])
            ),
            grouping_expressions=[],
            measures=[
                ee.aggregate_function(ARITH, "sum", [
                    ee.scalar_function(ARITH, "multiply", [
                        ee.column("l_extendedprice"),
                        ee.column("l_discount")
                    ])
                ])
            ]
        ),
        "SELECT SUM(l_extendedprice * l_discount) AS revenue FROM lineitem WHERE l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24")

def ex_tpch_q10_returned():
    """TPC-H Q10: Returned Item Reporting (simplified)."""
    return save("tpch_q10_returned.json",
        p.sort(
            p.fetch(
                p.aggregate(
                    p.filter(
                        p.join(
                            p.join(
                                p.read_named_table("customer", CUSTOMER_SCHEMA),
                                p.read_named_table("orders", ORDERS_SCHEMA),
                                ee.scalar_function(CMP, "equal", [
                                    ee.column(0),  # c_custkey
                                    ee.column(len(CUSTOMER_SCHEMA.names) + 1)  # o_custkey
                                ]),
                                stalg.JoinRel.JOIN_TYPE_INNER
                            ),
                            p.read_named_table("lineitem", LINEITEM_SCHEMA),
                            ee.scalar_function(CMP, "equal", [
                                ee.column(len(CUSTOMER_SCHEMA.names) + 0),  # o_orderkey
                                ee.column(len(CUSTOMER_SCHEMA.names) + len(ORDERS_SCHEMA.names) + 0)  # l_orderkey
                            ]),
                            stalg.JoinRel.JOIN_TYPE_INNER
                        ),
                        ee.scalar_function(CMP, "equal", [
                            ee.column(len(CUSTOMER_SCHEMA.names) + len(ORDERS_SCHEMA.names) + 8),  # l_returnflag
                            ee.literal("R", STR_REQ)
                        ])
                    ),
                    grouping_expressions=[
                        ee.column(0),   # c_custkey
                        ee.column(1),   # c_name
                        ee.column(5),   # c_acctbal
                    ],
                    measures=[
                        ee.aggregate_function(ARITH, "sum", [
                            ee.column(len(CUSTOMER_SCHEMA.names) + len(ORDERS_SCHEMA.names) + 5)  # l_extendedprice
                        ])
                    ]
                ),
                offset=None,
                count=ee.literal(20, INT64_REQ)
            ),
            [sort_field(3, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]
        ),
        "SELECT c_custkey, c_name, SUM(l_extendedprice*(1-l_discount)) AS revenue, c_acctbal FROM customer, orders, lineitem WHERE c_custkey = o_custkey AND l_orderkey = o_orderkey AND l_returnflag = 'R' GROUP BY c_custkey, c_name, c_acctbal ORDER BY revenue DESC LIMIT 20")

# ===========================================================================
# 12. Singular / multi or list
# ===========================================================================
def ex_singular_or_list():
    return save("singular_or_list.json",
        p.filter(
            p.read_named_table("orders", ORDERS_SCHEMA),
            ee.singular_or_list(ee.column("o_orderstatus"), [
                ee.literal("O", STR_REQ),
                ee.literal("P", STR_REQ),
                ee.literal("F", STR_REQ)
            ])
        ),
        "SELECT * FROM orders WHERE o_orderstatus IN ('O', 'P', 'F')")

# ===========================================================================
# 13. Cross join
# ===========================================================================
def ex_cross_join():
    return save("cross_join.json",
        p.cross(
            p.read_named_table("region", REGION_SCHEMA),
            p.read_named_table("nation", NATION_SCHEMA)
        ),
        "SELECT * FROM region CROSS JOIN nation")

# ===========================================================================
# 14. Project with computed columns
# ===========================================================================
def ex_project_computed():
    return save("project_computed.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [
                ee.column("l_orderkey"),
                ee.column("l_extendedprice"),
                ee.scalar_function(ARITH, "multiply", [
                    ee.column("l_extendedprice"),
                    ee.scalar_function(ARITH, "subtract", [
                        ee.literal(1.0, FP64_REQ),
                        ee.column("l_discount")
                    ])
                ])
            ]
        ),
        "SELECT l_orderkey, l_extendedprice, l_extendedprice * (1 - l_discount) AS net_price FROM lineitem")

def ex_project_string_ops():
    return save("project_string_ops.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [
                ee.column("c_custkey"),
                ee.scalar_function(STR_F, "upper", [ee.column("c_name")]),
                ee.scalar_function(STR_F, "char_length", [ee.column("c_name")])
            ]
        ),
        "SELECT c_custkey, UPPER(c_name), CHAR_LENGTH(c_name) FROM customer")

def ex_project_coalesce():
    return save("project_coalesce.json",
        p.project(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            [
                ee.column("c_custkey"),
                ee.scalar_function(CMP, "coalesce", [
                    ee.column("c_comment"),
                    ee.literal("N/A", STR_NULL)
                ])
            ]
        ),
        "SELECT c_custkey, COALESCE(c_comment, 'N/A') FROM customer")

# ===========================================================================
# 15. Additional variety
# ===========================================================================
def ex_partsupp_scan():
    return save("partsupp_scan.json",
        p.read_named_table("partsupp", PARTSUPP_SCHEMA),
        "SELECT * FROM partsupp")

def ex_filter_suppkey():
    return save("filter_suppkey.json",
        p.filter(
            p.read_named_table("partsupp", PARTSUPP_SCHEMA),
            ee.scalar_function(CMP, "equal", [ee.column("ps_suppkey"), ee.literal(42, INT64_REQ)])
        ),
        "SELECT * FROM partsupp WHERE ps_suppkey = 42")

def ex_agg_count_distinct_approx():
    from substrait.builders import extended_expression as ee2
    APPROX = "extension:io.substrait:functions_aggregate_approx"
    return save("agg_count_distinct_approx.json",
        p.aggregate(
            p.read_named_table("orders", ORDERS_SCHEMA),
            grouping_expressions=[],
            measures=[
                ee2.aggregate_function(APPROX, "approx_count_distinct", [ee.column("o_custkey")])
            ]
        ),
        "SELECT APPROX_COUNT_DISTINCT(o_custkey) FROM orders")

def ex_filter_ends_with():
    return save("filter_name_ends_with.json",
        p.filter(
            p.read_named_table("part", PART_SCHEMA),
            ee.scalar_function(STR_F, "ends_with", [ee.column("p_name"), ee.literal("green", STR_REQ)])
        ),
        "SELECT * FROM part WHERE p_name LIKE '%green'")

def ex_filter_contains():
    return save("filter_comment_contains.json",
        p.filter(
            p.read_named_table("supplier", SUPPLIER_SCHEMA),
            ee.scalar_function(STR_F, "contains", [ee.column("s_comment"), ee.literal("Customer", STR_REQ)])
        ),
        "SELECT * FROM supplier WHERE s_comment LIKE '%Customer%'")

def ex_agg_bool_and():
    return save("agg_bool_and.json",
        p.aggregate(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            grouping_expressions=[ee.column("l_returnflag")],
            measures=[
                ee.aggregate_function("extension:io.substrait:functions_boolean", "bool_and", [
                    ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(0.0, FP64_REQ)])
                ])
            ]
        ),
        "SELECT l_returnflag, BOOL_AND(l_quantity > 0) FROM lineitem GROUP BY l_returnflag")

def ex_sort_fetch_lineitem():
    return save("sort_fetch_lineitem.json",
        p.fetch(
            p.sort(
                p.read_named_table("lineitem", LINEITEM_SCHEMA),
                [sort_field(5, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]  # l_extendedprice
            ),
            offset=None,
            count=ee.literal(50, INT64_REQ)
        ),
        "SELECT * FROM lineitem ORDER BY l_extendedprice DESC LIMIT 50")

def ex_join_customer_nation():
    return save("join_customer_nation.json",
        p.join(
            p.read_named_table("customer", CUSTOMER_SCHEMA),
            p.read_named_table("nation", NATION_SCHEMA),
            ee.scalar_function(CMP, "equal", [
                ee.column(3),  # c_nationkey
                ee.column(len(CUSTOMER_SCHEMA.names) + 0)  # n_nationkey
            ]),
            stalg.JoinRel.JOIN_TYPE_INNER
        ),
        "SELECT * FROM customer INNER JOIN nation ON c_nationkey = n_nationkey")

def ex_filter_project_sort():
    return save("filter_project_sort.json",
        p.sort(
            p.select(
                p.filter(
                    p.read_named_table("orders", ORDERS_SCHEMA),
                    ee.scalar_function(CMP, "equal", [
                        ee.column("o_orderstatus"), ee.literal("O", STR_REQ)
                    ])
                ),
                [ee.column("o_orderkey"), ee.column("o_orderdate"), ee.column("o_totalprice")]
            ),
            [sort_field(2, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)]
        ),
        "SELECT o_orderkey, o_orderdate, o_totalprice FROM orders WHERE o_orderstatus = 'O' ORDER BY o_totalprice DESC")

def ex_if_then():
    return save("if_then.json",
        p.project(
            p.read_named_table("lineitem", LINEITEM_SCHEMA),
            [
                ee.column("l_orderkey"),
                ee.if_then(
                    [
                        (
                            ee.scalar_function(CMP, "gt", [ee.column("l_quantity"), ee.literal(30.0, FP64_REQ)]),
                            ee.literal("HIGH", STR_REQ)
                        )
                    ],
                    ee.literal("LOW", STR_REQ)
                )
            ]
        ),
        "SELECT l_orderkey, CASE WHEN l_quantity > 30 THEN 'HIGH' ELSE 'LOW' END FROM lineitem")

# ===========================================================================
# Run all examples
# ===========================================================================
examples = [
    # Simple scans
    ("lineitem_scan", ex_lineitem_scan),
    ("orders_scan", ex_orders_scan),
    ("customer_scan", ex_customer_scan),
    ("part_scan", ex_part_scan),
    ("supplier_scan", ex_supplier_scan),
    ("nation_scan", ex_nation_scan),
    ("region_scan", ex_region_scan),
    ("partsupp_scan", ex_partsupp_scan),
    # Projections
    ("lineitem_select_key_qty", ex_lineitem_select_key_qty),
    ("customer_select_name_seg", ex_customer_select_name_seg),
    ("orders_select_key_date", ex_orders_select_key_date),
    # Filters
    ("filter_quantity_gt", ex_filter_quantity_gt),
    ("filter_discount_lt", ex_filter_discount_lt),
    ("filter_orders_totalprice", ex_filter_orders_totalprice),
    ("filter_customer_acctbal_positive", ex_filter_customer_acctbal_positive),
    ("filter_is_null", ex_filter_is_null),
    ("filter_is_not_null", ex_filter_is_not_null),
    ("filter_and_compound", ex_filter_and_compound),
    ("filter_or_compound", ex_filter_or_compound),
    ("filter_not", ex_filter_not),
    ("filter_between", ex_filter_between),
    ("filter_like", ex_filter_like),
    ("filter_starts_with", ex_filter_starts_with),
    ("filter_three_conditions", ex_filter_three_conditions),
    ("filter_suppkey", ex_filter_suppkey),
    ("filter_ends_with", ex_filter_ends_with),
    ("filter_contains", ex_filter_contains),
    # Aggregations
    ("agg_count_all", ex_agg_count_all),
    ("agg_sum_qty", ex_agg_sum_qty),
    ("agg_avg_discount", ex_agg_avg_discount),
    ("agg_min_max_price", ex_agg_min_max_price),
    ("agg_group_by_returnflag", ex_agg_group_by_returnflag),
    ("agg_group_by_orderstatus", ex_agg_group_by_orderstatus),
    ("agg_group_by_mktsegment", ex_agg_group_by_mktsegment),
    ("agg_group_by_nationkey", ex_agg_group_by_nationkey),
    ("agg_count_distinct_approx", ex_agg_count_distinct_approx),
    ("agg_bool_and", ex_agg_bool_and),
    # Joins
    ("join_orders_customer_inner", ex_join_orders_customer_inner),
    ("join_lineitem_orders_inner", ex_join_lineitem_orders_inner),
    ("join_orders_customer_left", ex_join_orders_customer_left),
    ("join_nation_region", ex_join_nation_region),
    ("join_supplier_nation", ex_join_supplier_nation),
    ("join_partsupp_part", ex_join_partsupp_part),
    ("join_customer_nation", ex_join_customer_nation),
    # Sorts
    ("sort_lineitem_qty_asc", ex_sort_lineitem_qty_asc),
    ("sort_orders_totalprice_desc", ex_sort_orders_totalprice_desc),
    ("sort_customer_acctbal_desc", ex_sort_customer_acctbal_desc),
    ("sort_multi_column", ex_sort_multi_column),
    # Fetch
    ("fetch_top10", ex_fetch_top10),
    ("fetch_offset", ex_fetch_offset),
    # Combinations
    ("filter_project", ex_filter_project),
    ("filter_agg", ex_filter_agg),
    ("agg_sort", ex_agg_sort),
    ("filter_agg_sort_limit", ex_filter_agg_sort_limit),
    ("join_filter_select", ex_join_filter_select),
    ("sort_fetch_combined", ex_sort_fetch_combined),
    ("sort_fetch_lineitem", ex_sort_fetch_lineitem),
    ("filter_project_sort", ex_filter_project_sort),
    # String ops
    ("string_upper", ex_string_upper),
    ("string_lower", ex_string_lower),
    ("string_length", ex_string_length),
    ("string_concat", ex_string_concat),
    ("string_substring", ex_string_substring),
    ("string_trim", ex_string_trim),
    # Arithmetic
    ("arith_multiply", ex_arith_multiply),
    ("arith_revenue_with_tax", ex_arith_revenue_with_tax),
    ("arith_abs", ex_arith_abs),
    ("arith_negate", ex_arith_negate),
    ("round_ceil_floor", ex_round_ceil_floor),
    ("sqrt_power", ex_sqrt_power),
    # Computed projections
    ("project_computed", ex_project_computed),
    ("project_string_ops", ex_project_string_ops),
    ("project_coalesce", ex_project_coalesce),
    # Misc
    ("singular_or_list", ex_singular_or_list),
    ("cross_join", ex_cross_join),
    ("if_then", ex_if_then),
    # TPC-H queries
    ("tpch_q1_pricing_summary", ex_tpch_q1_pricing_summary),
    ("tpch_q3_shipping", ex_tpch_q3_shipping),
    ("tpch_q5_local_supplier", ex_tpch_q5_local_supplier),
    ("tpch_q6_revenue", ex_tpch_q6_revenue),
    ("tpch_q10_returned", ex_tpch_q10_returned),
]

print(f"Generating {len(examples)} examples to {OUTPUT_DIR} ...\n")
for name, fn in examples:
    gen(name, fn)

print(f"\nDone: {len(generated)} generated, {len(failed)} failed.")
if failed:
    print("\nFailed examples:")
    for name, err in failed:
        print(f"  {name}: {err}")
