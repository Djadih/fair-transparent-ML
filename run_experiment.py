import os
from model_utils import *
from survey_subject import SurveySubject, Query, RawQuery
import concurrent.futures


def init_log_file(name):
    with open(f"session_results/{name}_log.csv", 'w') as f:
        f.write(", Survey Log,")
        pass

def get_subject_info():
    print("--------------------")
    print("Beginning survey session... Training models in the background...")
    print("--------------------")

    subject_name = input("Please enter the subject's name/unique identifer: ")
    init_log_file(subject_name)
    subject_age = input("Please enter the subject's age: ")
    subject_gender = input("Please enter the subject's gender: ")
    subject_race = input("Please enter the subject's race: ")

    print("Thank you. Beginning survey as soon as models complete training...")
    return SurveySubject(subject_name, subject_age, subject_gender, subject_race)

def adversarial_debiasing_query(subject, model_list):
    # runs through the process of gathering user input to select the model, select the features,
    # and returning the output while logging the choices
    query_log = Query()


    model_names = ["Adversarial_Debiased", "Plain", "ExpGrad", "Gerry_Fair"]
    model_aliases = ["Albatross", "Beaver", "Chameleon", "Dragonfly"]

    # valid_model = False
    # while not valid_model:   Albatross  Dragonfly  Chameleon  Beaver
    #     try:
    #         model_choice = input("Which model should be used? [0: Albatross, 1: Beaver, 2: Chameleon, 3: Dragonfly, -1: End Session]: ")
    #         if model_choice not in ['0', '1', '2', '3', '-1', 'a', 'b', 'c', 'd']:
    #             raise Exception("Invalid input. Try again")
    #         valid_model = True
    #     except Exception:
    #         pass
    # if model_choice == '-1':
    #     print("Ending Session...")
    #     return False

    # model_choice_idx = int(model_choice) if model_choice.isdigit() else (ord(model_choice)-ord('a'))
    # model = model_list[model_choice_idx]
    # model_choice = model_names[model_choice_idx]
    # model_alias = model_aliases[model_choice_idx]
    # query_log.set_model_name(model_choice)

    continue_field = input("Would you like to continue the session? [y] or [n]: ")
    if continue_field == 'n':
        print("Ending Session...")
        return False

    all_inputs_valid = False
    while not all_inputs_valid:
        try:
            age_input = int(input("Indicate the person's age in years [0-99]: "))
            if age_input == -1:
                return False
            hrsperweek_input = input("Indicate the hours per week the person works [>0]: ")
            education_input = int(input("Indicate the person's number of years in education: [0-13]: "))
            marital_input = input("Indicate the person's marital status [Married, Divorced, Never married, Separated, Widowed]: ")
            occupation_input = input(
                """Indicate the person's occupation [Management, Business, Sciences, Health occupations, Education, Arts,
                Sales, Trades, Agriculture, Manufacturing]: """)

            raw_race_input = input("Indicate the person's race [White, Asian Pacific Islander, Black, American Indian, or Other]: ").lower()
            if raw_race_input == "white" or raw_race_input == "w":
                race_input = 1.0
            else:
                race_input = 0.0
            raw_sex_input = input("Indicate the person's gender: [m] or [f]: ")
            if raw_sex_input == 'f':
                sex_input = 0.0
            elif raw_sex_input == 'm':
                sex_input = 1.0
            workclass_input = input("Indicate the person's workclass [Private, Self-Employed, Government, Never worked]: ")
            all_inputs_valid = True
        except Exception:
            print("Error while parsing input. Try again")


    raw_query = RawQuery(modelType='all', inputs= {
        "Age"           : age_input,
        "Hours Per Week": hrsperweek_input,
        "Education"     : education_input,
        "Marital Status": marital_input,
        "Occupation"    : occupation_input,
        "Race"          : raw_race_input,
        "Sex"           : "Male" if raw_sex_input == "m" else "Female",
        "Workclass"     : workclass_input,
    })

    query_input = create_single_entry_adult_dataset(race_input, sex_input, age_input, education_input)
    query_log.set_featureNames(query_input.feature_names)
    query_log.set_features(query_input.features)
    pred_list = predict_income_adversarial_debiasing(model_list[0:3], query_input)

    gerry_input = create_single_entry_adult_dataset(race_input, sex_input, age_input, education_input, model_type="Gerry_Fair")
    # pred_list.append(predict_income_adversarial_debiasing(model_list[3:3], gerry_input)[0])
    gerry_pred = predict_income_adversarial_debiasing(model_list[3:4], gerry_input)
    print(" ")
    pred_list.append(gerry_pred[0])

    for i, pred in enumerate(pred_list):
        query_log.set_output(pred)
        
        raw_query = RawQuery(modelType=model_aliases[i], inputs= {
        "Age"           : age_input,
        "Hours Per Week": hrsperweek_input,
        "Education"     : education_input,
        "Marital Status": marital_input,
        "Occupation"    : occupation_input,
        "Race"          : raw_race_input,
        "Sex"           : "Male" if raw_sex_input == "m" else "Female",
        "Workclass"     : workclass_input,
        })
        raw_query.set_output("LESS" if pred == 0.0 else "MORE")
        subject.log_completed_query(raw_query, query_log)


    return True

def run_experiment():
    # Implemented multi-threading so that the user can query the model while the model is training.
    with concurrent.futures.ThreadPoolExecutor() as executor:
        subject_info_t = executor.submit(get_subject_info)

        privileged_groups = [{'sex': 0, 'race': 0}]
        unprivileged_groups = [{'sex': 1, 'race': 1}]

        dataset_orig = load_preproc_data_adult()

        plain_model = plain_training(dataset_orig, privileged_groups, unprivileged_groups)
        adversarial_model = adversarial_debiasing(dataset_orig, privileged_groups, unprivileged_groups)
        expgrad_model = exponentiated_gradient_reduction(dataset=dataset_orig, constraints="DemographicParity")
        gerryfair_model = gerry_fair_trained_model(dataset_orig)

        all_models = [adversarial_model, plain_model, expgrad_model, gerryfair_model]
        print("Training completed!")
        subject = subject_info_t.result()

    # allow the user to input their own queries
    continue_session = True
    while continue_session:
        continue_session = adversarial_debiasing_query(subject, all_models)
        subject.save_session_raw_queries()

    # prompt for rankings
    rankings = prompt_for_ranking()

    # Save queries and results
    subject.save_session_data(rankings)
    subject.print_all_queries()
    return

if __name__ == "__main__":
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    run_experiment()