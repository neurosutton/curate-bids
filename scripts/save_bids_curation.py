#!/usr/bin/env python3
"""Save BIDS mapping from acquisition names to BIDS paths and fieldmap IntendedFors as sorted csv files.

Note that you need to be logged in to a Flywheel instance using the CLI (fw login ...)

INTENDED_FOR is a space separated pair of regular expressions, the first one matches the fieldmap file name and the second of each pair matches the BIDS filename.

Example with --intended-for parameter:
   save_bids_curation.py  Group Project -i '.*fmap(_|-)SE(_|-).*' '_run-1' '.*gre.+_e[12]\.' '_run-2' '.*gre.+_ph' '_run-2'
"""

import argparse
import csv
import pandas as pd
import os
import re

import flywheel


def make_file_name_safe(input_basename, replace_str=""):
    """Remove non-safe characters from a filename and return a filename with
        these characters replaced with replace_str.

    :param input_basename: the input basename of the file to be replaced
    :type input_basename: str
    :param replace_str: the string with which to replace the unsafe characters
    :type   replace_str: str
    :return: output_basename, a safe
    :rtype: str
    """

    safe_patt = re.compile(r"[^A-Za-z0-9_\-.]+")
    # if the replacement is not a string or not safe, set replace_str to x
    if not isinstance(replace_str, str) or safe_patt.match(replace_str):
        print("{} is not a safe string, removing instead".format(replace_str))
        replace_str = ""

    # Replace non-alphanumeric (or underscore) characters with replace_str
    safe_output_basename = re.sub(safe_patt, replace_str, input_basename)

    if safe_output_basename.startswith("."):
        safe_output_basename = safe_output_basename[1:]

    print('"' + input_basename + '" -> "' + safe_output_basename + '"')

    return safe_output_basename


def do_print(msg):

    if args.verbose > 0:
        print(msg)


def save_curation_csvs(fw, group_label, project_label):
    """Save BIDS mapping from acquisition names to BIDS paths and fieldmap IntendedFors.

    Two csv files, sorted by subject, will be saved.

    Args:
        fw (flywheel.client.Client): active Flywheel client
        group_label (str) Group ID (label, not Group name)
        project_label (str) Project label

    Returns: nothing
    """

    project = fw.projects.find_one(f"group={group_label},label={project_label}")

    acquisition_labels = dict()

    all_intended_for_acq_label = dict()
    all_intended_for_acq_id = dict()
    all_intended_for_dirs = dict()
    all_intended_fors = dict()

    all_seen_paths = dict()

    num_duplicates = 0

    all_df = pd.DataFrame(
        columns=(
            "SeriesNumber",
            "Acquisition label (SeriesDescription)",
            "File name",
            "File type",
            "Curated BIDS path",
        )
    )

    # Look through all files in the project and get their BIDS path
    for subject in project.subjects.iter_find():

        do_print(subject.label)

        intended_for_acq_label = dict()
        intended_for_acq_id = dict()
        intended_for_dirs = dict()
        intended_fors = dict()

        nifti_df = pd.DataFrame(
            columns=(
                "SeriesNumber",
                "Subject",
                "Session",
                "Acquisition label (SeriesDescription)",
                "File name",
                "File type",
                "Curated BIDS path",
                "Unique?",
            )
        )

        ii = 0  # Current acquisition index

        seen_paths = dict()

        for session in subject.sessions():
            for acquisition in session.acquisitions():

                do_print(f"{ii}  {acquisition.label}")

                if acquisition.label in acquisition_labels:
                    acquisition_labels[acquisition.label] += 1
                else:
                    acquisition_labels[acquisition.label] = 1

                for file in acquisition.reload().files:

                    # determine full BIDS path
                    if "BIDS" in file.info:
                        if file.info["BIDS"] == "NA":
                            bids_path = "nonBids"
                        else:
                            bids_path = ""
                            expected = ["ignore", "Folder", "Filename"]
                            for key in expected:
                                if key not in file.info["BIDS"]:
                                    bids_path += f"missing_{key} "
                            if bids_path == "":
                                if file.info["BIDS"]["ignore"]:
                                    bids_path = "ignored"
                                else:
                                    bids_path = (
                                        f"{file.info['BIDS']['Folder']}/"
                                        + f"{file.info['BIDS']['Filename']}"
                                    )
                        if "IntendedFor" in file.info and len(file.info["IntendedFor"]) > 0:
                            intended_fors[file.name] = file.info["IntendedFor"]
                            intended_for_acq_label[file.name] = acquisition.label
                            intended_for_acq_id[file.name] = acquisition.id
                            if "IntendedFor" in file.info["BIDS"]:
                                intended_for_dirs[file.name] = file.info["BIDS"]["IntendedFor"]
                            else:
                                # This only happens when a previous curation run had folder(s) here
                                # but this one does not.
                                intended_for_dirs[file.name] = [{"Folder": "folder is missing"}]
                    else:
                        bids_path = "Not_yet_BIDS_curated"

                    if "SeriesNumber" in file.info:
                        series_number = file.info["SeriesNumber"]
                    else:
                        series_number = "?"

                    # Detect Duplicates
                    if bids_path in ["ignored", "nonBids", "Not_yet_BIDS_curated"]:
                        unique = ""
                    elif bids_path in seen_paths:
                        seen_paths[bids_path] += 1
                        unique = f"duplicate {seen_paths[bids_path]}"
                        num_duplicates += 1
                    else:
                        seen_paths[bids_path] = 0
                        unique = "unique"

                    do_print(
                        f"{series_number}, {subject.label}, {session.label}, "
                        f"{acquisition.label}, {file.name}, {file.type}, "
                        f"{bids_path}, {unique}"
                    )

                    nifti_df.loc[ii] = [
                        series_number,
                        subject.label,
                        session.label,
                        acquisition.label,
                        file.name,
                        file.type,
                        bids_path,
                        unique,
                    ]
                    ii += 1

        nifti_df.sort_values(by=["Curated BIDS path"], inplace=True)

        all_df = all_df.append(nifti_df)

        all_intended_for_acq_label[subject.label] = intended_for_acq_label
        all_intended_for_acq_id[subject.label] = intended_for_acq_id
        all_intended_for_dirs[subject.label] = intended_for_dirs
        all_intended_fors[subject.label] = intended_fors

        all_seen_paths[subject.label] = seen_paths

    safe_group_label = make_file_name_safe(group_label, replace_str="_")
    safe_project_label = make_file_name_safe(project_label, replace_str="_")

    # Save acquisition/file name -> bids path mapping
    all_df.to_csv(f"{safe_group_label}_{safe_project_label}_niftis.csv", index=False)

    do_print("")

    # save field map IntendedFor lists
    with open(
        f"{safe_group_label}_{safe_project_label}_intendedfors.csv", mode="w"
    ) as intendedfors_file:
        intendedfors_writer = csv.writer(
            intendedfors_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
        )

        if args.verbose > 0:
            intendedfors_writer.writerow(["Initial values (before correction)"])
            intendedfors_writer.writerow(
                [
                    "acquisition label",
                    "file name and folder",
                    "IntendedFor List of BIDS paths",
                ]
            )

            for subj in all_intended_for_dirs:

                for k, v in all_intended_for_dirs[subj].items():
                    do_print(f"{all_intended_for_acq_label[subj][k]}, {k}")
                    intendedfors_writer.writerow(
                        [all_intended_for_acq_label[subj][k], k]
                    )
                    for i in v:
                        do_print(f",{i['Folder']}")
                        intendedfors_writer.writerow(["", i["Folder"]])
                        all_intended_fors[subj][k].sort()
                        for j in all_intended_fors[subj][k]:
                            do_print(f",,{j}")
                            intendedfors_writer.writerow(["", "", j])

        # Keep only proper file paths if they match fieldmaps as per provided regexes
        if args.intended_for:

            string_pairs = zip(args.intended_for[::2], args.intended_for[1::2])
            # for pair in string_pairs:
            #    print(f"fmap regex \"{pair[0]}\" will correct file \"{pair[1]}\"")

            regex_pairs = list()
            for s_p in string_pairs:
                regex_pairs.append([re.compile(s_p[0]), re.compile(s_p[1])])

            new_intended_fors = dict()

            for subj in all_intended_for_dirs:

                new_intended_fors[subj] = dict()

                for file_name in all_intended_for_dirs[subj]:
                    print(f"{file_name}")
                    for regex in regex_pairs:
                        if regex[0].search(file_name):
                            new_intended_fors[subj][file_name] = list()
                            for i_f in all_intended_fors[subj][file_name]:
                                if regex[1].search(i_f):
                                    new_intended_fors[subj][file_name].append(i_f)
                                    print(f"found {i_f}")
                            fw.modify_acquisition_file_info(
                                all_intended_for_acq_id[subj][file_name],
                                file_name,
                                {
                                    "set": {
                                        "IntendedFor": new_intended_fors[subj][
                                            file_name
                                        ]
                                    }
                                },
                            )
        else:
            new_intended_fors = all_intended_fors

        if args.verbose > 0:
            intendedfors_writer.writerow(["Final values (after correction)"])

        # write out final values of IntendedFor lists
        intendedfors_writer.writerow(
            [
                "",
                "",
                "",
            ]
        )
        intendedfors_writer.writerow(
            [
                "acquisition label",
                "file name and folder",
                "IntendedFor List of BIDS paths",
            ]
        )
        for subj in all_intended_for_dirs:

            for k, v in all_intended_for_dirs[subj].items():
                do_print(f"{all_intended_for_acq_label[subj][k]}, {k}")
                intendedfors_writer.writerow([all_intended_for_acq_label[subj][k], k])
                for i in v:
                    do_print(f",{i['Folder']}")
                    intendedfors_writer.writerow(["", i["Folder"]])
                    # new_intended_fors[subj][k].sort()
                    for j in new_intended_fors[subj][k]:
                        do_print(f",,{j}")
                        intendedfors_writer.writerow(["", "", j])

    # save acquisition labels count list
    with open(
        f"{safe_group_label}_{safe_project_label}_acquisitions.csv", mode="w"
    ) as acquisition_file:
        acquisition_writer = csv.writer(
            acquisition_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
        )

        acquisition_writer.writerow(["acquisition label", "count"])

        for label, count in acquisition_labels.items():
            acquisition_writer.writerow([label, count])

    if num_duplicates > 0:
        print("ERROR: the following BIDS paths appear more than once:")
        for subject in project.subjects.iter_find():
            for path in all_seen_paths[subject.label]:
                if all_seen_paths[subject.label][path] > 0:
                    print(f"  {path}")
    else:
        print("No duplicates were found.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("group_label", help="fw://group_label/project_label")
    parser.add_argument("project_label", help="fw://group_label/project_label")
    parser.add_argument('-a', '--api-key', action='store', type=str,
                        help='api-key (default is to use currently logged in instance')
    parser.add_argument(
        "-i",
        "--intended-for",
        action="store",
        nargs="*",
        type=str,
        help="pairs of regex's specifying field map file name to BIDS Filename",
    )

    parser.add_argument("-v", "--verbose", action="count", default=0)

    args = parser.parse_args()

    # This works if you are logged into a Flywheel instance on a Terminal:
    if args.api_key:
        fw = flywheel.Client(api_key=args.api_key, root=True)
    else:
        fw = flywheel.Client("", root=True)

    # Prints the instance you are logged into to make sure it is the right one.
    print(fw.get_config().site.api_url)

    save_curation_csvs(fw, args.group_label, args.project_label)

    os.sys.exit(0)
