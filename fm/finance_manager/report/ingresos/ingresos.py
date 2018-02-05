# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import getdate, cint
import calendar

def execute(filters=None):
	# key yyyy-mm
	new_clients = {}
	payments = {}
	rows = []
	company_condition = ""
	totals = []

	if filters.get("company"):
		company_condition = 'AND company=%(company)s'

	result = frappe.db.sql("""
		SELECT
			posting_date,
			MONTH(posting_date) mo,
			YEAR(posting_date) yr,
			EXTRACT(YEAR_MONTH FROM posting_date) AS yearmonth,
			SUM(total_debit) AS total,
			COUNT(name) records
		FROM
			`tabJournal Entry` 
		WHERE
			docstatus = 1 
			AND es_un_pagare = 1
			{company_condition}
		GROUP BY
			yearmonth 
		HAVING
			posting_date BETWEEN %(from_date)s AND %(to_date)s 
		ORDER BY
			posting_date
		""".format(company_condition=company_condition),
	filters, as_dict=True)

	for row in result:
		key = row.posting_date.strftime("%Y-%m")
		# rows.append([row.yr, row.mo, row.total, row.records])
		payments.setdefault(key, [0.000, 0.000, 0.000])
		# payments[key][0] += 1
		payments[key][0] += row.records
		payments[key][1] += row.total
		# payments[key][3] += row.total

	# time series
	from_year, from_month, temp = filters.get("from_date").split("-")
	to_year, to_month, temp = filters.get("to_date").split("-")

	from_year, from_month, to_year, to_month = \
		cint(from_year), cint(from_month), cint(to_year), cint(to_month)

	out = []
	for year in xrange(from_year, to_year +1):
		for month in xrange(from_month if year==from_year else 1, (to_month+1) if year==to_year else 12):
			key = "{year}-{month:02d}".format(year=year, month=month)

			jv = payments.get(key, [0.000, 0.000, 0.000])

			out.append([year, calendar.month_name[month], jv[0], jv[1]])

	return [
		_("Year"), _("Month"),
		_("Payments") + ":Int:150",
		_("Total Revenue") + ":Currency:150",
	], out


