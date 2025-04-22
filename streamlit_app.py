import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.express as px
import json

st.set_page_config(layout="wide", page_title="Admissions Analysis", page_icon="🎓")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Homepage",
        "Overview",
        "Municipality Analysis",
        "University Analysis",
        "Application Timing",
    ],
)

# Main dataframe
df = duckdb.sql(
    f"""
    SELECT
        applications.application_id,
        applications.person_id,
        applications.priority_number,
        applications.program_id,
        applications.financing,
        applications.financing IN ('Financed', 'Stipend') AND applications.invited AS financed_invitation,
        applications.invited,
        applications.signed,
        applications.choice_at,
        applications.stage_start_date,
        applications.stage_end_date,
        profiles.gender,
        profiles.residence_municipality,
        profiles.residence_type,
        profiles.residence_place,
        programs.program_name_en,
        programs.educational_institution,
        sum(applications.invited) over (partition by applications.person_id) as was_invited_to_any_choice
    FROM 'admissions/applications.parquet' applications
    LEFT JOIN 'admissions/profiles.parquet' profiles
        ON applications.person_id = profiles.person_id
        AND year(applications.stage_start_date) = profiles.application_year
    LEFT JOIN 'admissions/programs.parquet' programs
        ON applications.program_id = programs.program_id
        AND year(applications.stage_start_date) = year(programs.program_year)
    WHERE  applications.admission_stage = 'Main Admission'
    AND applications.participated_in_competition
    AND year(applications.stage_start_date) = 2024
"""
).df()

df["choice_hour"] = df["choice_at"].dt.hour
df["choice_dayofweek"] = df["choice_at"].dt.dayofweek
df["choice_date"] = df["choice_at"].dt.date
df["stage_start_date"] = df["stage_start_date"].dt.date
df["stage_end_date"] = df["stage_end_date"].dt.date
df["choice_week"] = df["choice_at"].dt.to_period("W").dt.start_time.dt.date


def get_unique_values(column):
    return (
        df.groupby(column)["person_id"]
        .nunique()
        .sort_values(ascending=False)
        .index.tolist()
    )


with tab1:
    st.title("Lithuanian Higher Education Admissions Analysis")
    st.markdown(
        "This webpage contains an interactive analysis of Lithuanian Higher Education Admissions (LAMA BPO) Dataset. "
        "You can find more information about the dataset [here](https://data.gov.lt/datasets/2914/). "
        "Column names and some of values for some of the columns were translated to English."
    )
    st.divider()
    st.markdown(
        "Here is a sample of the preprocessed dataset used in this analysis. One row is one unique application (application_id). "
        "A single application is also uniquely identified by (person_id, priority_number, program_id, financing). "
    )
    st.dataframe(df.sample(20))
    st.divider()
    with open("admissions/docs.md", "r") as f:
        st.expander("See dataset documentation").markdown(f.read())


with tab2:
    groupby = st.selectbox(
        "Group by", options=["educational_institution", "residence_municipality"]
    )
    filter_values = get_unique_values(groupby)

    filter_choices = st.multiselect("Filter", options=filter_values, placeholder="All")
    if not filter_choices:
        filter_choices = filter_values
    condition = df[groupby].isin(filter_choices)

    st.markdown(f"### Key metrics by {groupby}")

    df_agg = (
        df[condition]
        .groupby(groupby)
        .agg(
            count=("person_id", "nunique"),
            invited=("invited", "sum"),
            signed=("signed", "sum"),
            financed_invitation=("financed_invitation", "sum"),
        )
        .sort_values("count", ascending=False)
    )

    df_agg["invitation_rate"] = df_agg["invited"] / df_agg["count"]
    df_agg["signed_rate"] = df_agg["signed"] / df_agg["invited"]
    df_agg["financed_invitation_rate"] = (
        df_agg["financed_invitation"] / df_agg["invited"]
    )

    df_agg = df_agg[
        ["count", "invitation_rate", "signed_rate", "financed_invitation_rate"]
    ]

    df_agg = df_agg.style.background_gradient(
        subset=["invitation_rate", "signed_rate", "financed_invitation_rate"],
        cmap="RdYlGn",
        axis=0,
    ).format("{:.2f}")

    st.dataframe(df_agg)


with tab3:
    col1, col2 = st.columns([0.3, 0.7])

    with col1:
        st.markdown("### Description")
        st.markdown(
            "This tab contains an analysis of the applications by municipality. "
            "Filter a specific municipality using the filter below. "
        )

        st.markdown("### Filters")
        municipality = st.selectbox(
            "Select municipality",
            get_unique_values("residence_municipality"),
            index=get_unique_values("residence_municipality").index("Vilniaus m. sav."),
        )

        df_filtered = df[df["residence_municipality"] == municipality].copy()

    with col2:

        ## Metrics
        applicants_count = df_filtered["person_id"].nunique()
        invited_count = df_filtered["invited"].sum()
        signed_count = df_filtered["signed"].sum()
        invitation_rate = np.round(invited_count / applicants_count, 2)
        signed_rate = np.round(signed_count / invited_count, 2)

        cols = st.columns(5)
        with cols[0]:
            st.metric(
                "Total Applicants",
                applicants_count,
                help="Total number of unique applicants",
            )
        with cols[1]:
            st.metric(
                "Total Invited",
                invited_count,
                help="Total number of invited applicants",
            )
        with cols[2]:
            st.metric(
                "Invitation Rate",
                invitation_rate,
                help="Ratio of invited applicants to total applicants",
            )
        with cols[3]:
            st.metric(
                "Total Signed", signed_count, help="Total number of signed applicants"
            )
        with cols[4]:
            st.metric(
                "Signed Rate",
                signed_rate,
                help="Ratio of signed applicants to invited applicants",
            )

        st.divider()

        ## Programs Table
        st.markdown("### Programs Overview")

        programs_invited = (
            df_filtered[df_filtered["invited"]].groupby("program_name_en").size()
        )

        programs_applied = (
            df_filtered[
                (df_filtered["priority_number"] == 1)
                & (df_filtered["was_invited_to_any_choice"] == 1)
            ]
            .groupby("program_name_en")
            .size()
        )
        programs_comparison = (
            pd.DataFrame(
                {"invited": programs_invited, "applied_as_first": programs_applied}
            )
            .fillna(0)
            .astype(int)
            .sort_values("invited", ascending=False)
        )

        programs_comparison["ratio"] = (
            programs_comparison["applied_as_first"] / programs_comparison["invited"]
        )
        st.dataframe(
            programs_comparison.style.background_gradient(
                subset=["ratio"], cmap="RdYlGn", vmin=0, vmax=2
            ).format({"ratio": "{:.2f}"})
        )
        st.expander("See explanation").markdown(
            """
            The table above shows how many applicants applied to a specific program, as well as how many of them were invited.
            The ratio column shows the ratio of applied applicants to invited applicants.
            """
        )

        ## Residence Type Table
        st.markdown("### Residence Type x Gender")

        df_invited = df_filtered[df_filtered["invited"]]

        residence_totals = df_invited.groupby("residence_type")["person_id"].nunique()

        df_gender_residence = (
            df_invited.groupby(["residence_type", "financing"])
            .agg(count=("person_id", "nunique"))
            .reset_index()
        )

        df_gender_residence["share"] = df_gender_residence.apply(
            lambda x: x["count"] / residence_totals[x["residence_type"]], axis=1
        )

        fig = px.bar(
            df_gender_residence,
            x="residence_type",
            y="share",
            color="financing",
            barmode="group",
        )
        fig.update_layout(
            xaxis_title="Residence Type",
            yaxis_title="Share of Applicants",
            xaxis_tickfont_size=15,
            legend_font_size=15,
            legend_title_font_size=15,
        )

        st.plotly_chart(fig)
        st.expander("See explanation").markdown(
            """
            The chart above shows the number of applicants by financing type and gender.

            """
        )


with tab4:
    col1, col2 = st.columns([0.3, 0.7])

    with col1:

        st.markdown("### Description")
        st.markdown(
            "This tab contains an analysis of the applications by educational institution. "
            "Filter a specific educational institution using the filter below. "
        )

        st.markdown("### Filters")
        ed_inst = st.selectbox(
            "Select educational institution",
            get_unique_values("educational_institution"),
        )
        metric = st.pills(
            "Select metric for the map",
            options=["count", "invited_rate", "signed_rate"],
            selection_mode="single",
            default="count",
        )

    with col2:
        st.markdown("### Geographic Distribution of Applicants")
        condition = df["educational_institution"] == ed_inst
        df_agg = (
            df[condition]
            .groupby("residence_municipality")
            .agg(
                count=("person_id", "nunique"),
                invited_count=("invited", "sum"),
                signed_count=("signed", "sum"),
            )
            .reset_index()
        )

        df_agg["invited_rate"] = df_agg["invited_count"] / df_agg["count"]
        df_agg["signed_rate"] = df_agg["signed_count"] / df_agg["invited_count"]

        with open("lt_municipalities_geo.json", "r") as f:
            lt_geojson = json.load(f)

        fig = px.choropleth_mapbox(
            df_agg,
            geojson=lt_geojson,
            locations="residence_municipality",
            featureidkey="properties.name",
            color=metric,
            zoom=6,
            center={"lat": 55.1694, "lon": 23.8813},
            mapbox_style="carto-positron",
        )

        fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
        st.plotly_chart(fig)

        st.markdown("### Competitors")
        st.caption(
            f"Which other universities did applicants to {ed_inst} also apply to? "
        )
        students = df[df["educational_institution"] == ed_inst]["person_id"].unique()
        df_competitors = (
            df[
                df["person_id"].isin(students)
                & (df["educational_institution"] != ed_inst)
            ]
            .groupby("educational_institution")
            .agg(count=("person_id", "nunique"))
            .sort_values("count", ascending=False)
        )

        st.dataframe(df_competitors)

with tab5:
    col1, col2 = st.columns([0.3, 0.7])

    with col1:
        st.markdown("### Description")
        st.write(
            f"Main admissions started on {df['stage_start_date'].min()} and ended on {df['stage_end_date'].max()}. "
            "The number of applications submitted per day is shown below."
        )

        st.markdown("### Filters")
        municipality = st.selectbox(
            "Select municipality to compare",
            options=get_unique_values("residence_municipality"),
        )

    with col2:
        condition = df["residence_municipality"] == municipality
        df_all = df.groupby("choice_date").size().reset_index(name="count")
        df_all["share"] = df_all["count"] / df_all["count"].sum()
        df_all["group"] = "All municipalities"

        df_choice = (
            df[condition].groupby("choice_date").size().reset_index(name="count")
        )
        df_choice["share"] = df_choice["count"] / df_choice["count"].sum()
        df_choice["group"] = municipality

        df_plot = pd.concat([df_all, df_choice])

        fig = px.line(
            df_plot,
            x="choice_date",
            y="share",
            color="group",
            title="Application Timing Distribution",
            labels={"choice_date": "Date", "share": "Share of Applications"},
            height=600,
        )

        st.plotly_chart(fig)
