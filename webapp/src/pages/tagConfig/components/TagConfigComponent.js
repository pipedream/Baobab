import React, { Component } from "react";
import { tagsService } from "../../../services/tags";
import { Link } from "react-router-dom";
import { withRouter } from "react-router";
import { withTranslation } from 'react-i18next';
import FormTextBox from "../../../components/form/FormTextBox";
import FormTextArea from "../../../components/form/FormTextArea";
import FormSelect from "../../../components/form/FormSelect";

const TAG_TYPES = ["RESPONSE", "REGISTRATION"];

class TagConfigComponent extends Component {
  constructor(props) {
    super(props);

    this.state = {
      tags: [],
      updatedTag: {
        name: {},
        tag_type: "",
        description: {},
        language: ""
      },
      isMultiLingual: this.props.organisation.languages.length > 1,
      isValid: false,
      loading: false,
      error: "",
      errors: [],
      showErrors: false,
      tagEntryVisible: false
    };
  }

  componentDidMount() {
    if (this.props.event) {
      tagsService.getTagList(this.props.event.id).then(result => {
        this.setState({
          loading: false,
          tags: result.tags,
          error: result.error
        });
        console.log(this.state.tags);
      });
    }
  }

  onClickAdd = () => {
    const errors = []; //TDDO, validate tag
    if (errors.length === 0) {
      tagsService.addTag(this.state.updatedTag).then(result => {
        if (result.error) {
          this.setState({
            errors: [this.props.t(result.error)],
            showErrors: true
          });
        }
        else {
          //this.props.history.goBack();
        }});
    }
    else {
      this.setState({
        showErrors: true
      });
    }
  };

  onClickUpdate = () => {
    const errors = []; //TODO, validate tag
    if (errors.length === 0) {
      tagsService.updateTag(this.state.updatedTag).then(result => {
        if (result.error) {
          this.setState({
            errors: [this.props.t(result.error)],
            showErrors: true
          });
        }
        else {
          //go back to tag table
        }});
    }
    else {
      this.setState({
        showErrors: true
      });
    }
  };

  onClickDelete = () => {
    const tag = null; //TODO
    tagsService.deleteTag(tag).then(result => { //TODO: will fail, need to add deleteTag to tagsService
      if (result.error) {
        this.setState({
          errors: [this.props.t(result.error)],
          showErrors: true
        });
      }
      else {
        //go back to tag table
      }});
  }

  getErrorMessages = errors => {
    const errorMessages = [];

    for (let i = 0; i < errors.length; i++) {
      errorMessages.push(
        <div key={"error_"+i} className={"alert alert-danger alert-container"}>
          {errors[i]}
        </div>
      );
    }
    return errorMessages;
  };

  validateTag = (tag) => {
    let errors = [];
    if (tag.name.length === 0) {
      errors.push(this.props.t("Tag name is required"));
    }
    if (tag.type.length === 0) {
      errors.push(this.props.t("Tag type is required"));
    }
    return errors;
  };

  updateTextField = (fieldName, e, lang) => {
    let u;
    if (lang) {
      u = {
        ...this.state.updatedTag,
        [fieldName]: {
          ...this.state.updatedTag[fieldName],
          [lang]: e.target.value
        }
      };
    }
    else {
      u = {
        ...this.state.updatedTag,
        [fieldName]: e.target.value
      };
    }
    this.updateState(u);
  };

  updateDropDown = (fieldName, dropdown) => {
    const u = {
      ...this.state.updatedTag,
      [fieldName]: dropdown.value
    };
    this.updateState(u);
  };

  updateState = (tag) => {
    this.setState({
      updatedTag: tag
    }, () => {

      const errors = [];//this.validateEventDetails();

      this.setState({
        //allFieldsComplete: this.areAllFieldsComplete(),
        errors: errors,
        isValid: errors.length === 0
      });
    });
  }

  renderTagTable = () => {
    const tagRows = [];
    const t = this.props.t;
    const tags = this.state.tags;
    tagRows.push(<h3>{t("Tags")}</h3>)
    for (let i = 0; i < tags.length; i++) {
      const tag = tags[i];
      tagRows.push(
        <div className="tag">
          <div className="tag-info">
            {tag.name}
          </div>
        </div>
      );
    }

    //TODO
    return tagRows
    return <div></div>;
  }

  renderTagEntry = () => {
    const t = this.props.t;
    const tagEntryForm = [];
    tagEntryForm.push(
      <div className={"form-group row"}>
        <label
          className={"col-sm-2 col-form-label"}
          htmlFor={"tag_type"}>
          <span className="required-indicator">*</span>
          {t("Tag Type")}
        </label>
        <div className="col-sm-10">
          <FormSelect
            id={"tag_type"}
            name={"tag_type"}
            required={true}
            defaultValue={this.state.updatedTag.tag_type || null}
            onChange={this.updateDropDown}
            options={
              TAG_TYPES.map((tagType) => ({
                value: tagType,
                label: t(tagType)
              }))
            }
          />
        </div>
      </div>
    );
    tagEntryForm.push(
    this.props.organisation.languages.map((lang) => (
      <div>
      <div className={"form-group row"} key={"name_div"+lang.code}>
        <label
        className={"col-sm-2 col-form-label"} 
        htmlFor={"name_" + lang.code}>
        <span className="required-indicator">*</span>
        {this.state.isMultiLingual ? t(this.getFieldNameWithLanguage("Tag Name", lang.description)) : t("Tag Name")}
        </label>
        <div className="col-sm-10">
          <FormTextBox
          id={"name_" + lang.code}
          name={"name_" + lang.code}
          type="text"
          placeholder={this.state.isMultiLingual ? t(this.getFieldNameWithLanguage("Name of the tag", lang.description)) : t("Name of the tag")}
          required={true}
          onChange={e => this.updateTextField("name", e, lang.code)}
          value={this.state.updatedTag.name[lang.code]}
        />
        </div>
      </div>
      <div className={"form-group row"} key={"description_div"+lang.code}>
        <label
          className={"col-sm-2 col-form-label"}
          htmlFor={"description"}>
          {this.state.isMultiLingual ? t(this.getFieldNameWithLanguage("Tag Name", lang.description)) : t("Tag Description")}
        </label>
        <div className="col-sm-10">
          <FormTextArea
            id={"description"}
            name={"description"}
            type="text"
            placeholder={t("Description of the tag")}
            required={false}
            onChange={e => this.updateTextField("description", e, lang.code)}
            value={this.state.updatedTag.description[lang.code]}
          />
        </div>
      </div>
    </div>
    )));

    tagEntryForm.push(
      <div className={"form-group row"}>
        <button className="btn btn-primary" onClick={this.onClickAdd()}>
          {t("Save")}
        </button>
      </div>
    );
    console.log(this.state);
    return tagEntryForm;
  }

  setTagEntryVisible = () => {
    this.setState({
      tagEntryVisible: true
      });
  }

  getFieldNameWithLanguage = (input, lang) => {
    return input + " in " + lang;
  }

  render() {
    const {
      loading,
      error,
      tagEntryVisible
    } = this.state;

    const loadingStyle = {
      width: "3rem",
      height: "3rem"
    };

    if (loading) {
      return (
        <div className="d-flex justify-content-center">
          <div className="spinner-border"
            style={loadingStyle}
            role="status">
            <span className="sr-only">Loading...</span>
          </div>
        </div>
      );
    }

    if (error) {
      return <div className="alert alert-danger alert-container">
        {error}
      </div>;
    }

    const t = this.props.t;
    //console.log(this.props.user);
    //console.log(this.props.user.is_admin);

    return (
      <div>
        <div className="card">
          <form>
          {this.renderTagTable()}
          {
            <a onClick={this.setTagEntryVisible} id="new_tag_button" name="new_tag_button" className="btn btn-primary">{t("New Tag")}</a>
          }
          {tagEntryVisible && this.renderTagEntry()}
          {this.state.showErrors && this.getErrorMessages(this.state.errors)}
          </form>
        </div>
      </div>)        
  }
}

export default withRouter(withTranslation()(TagConfigComponent));
