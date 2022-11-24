#!/usr/bin/env bash



for joined_dir in $(fd Joined .);
do
    for kern_path in $(fd '.*\.krn$' "${joined_dir}"); do
        result=$(/Users/malcolm/google_drive/c++/humlib/bin/find_missing_pitches "${kern_path}")
        if [[ -n "${result}" ]]; then
            echo $result
            echo $kern_path
        fi
    done
done
